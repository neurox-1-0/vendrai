import asyncio
import time
import uuid
from datetime import UTC, datetime

import httpx
from app.agents.execution import execute_parallel
from app.agents.planning import (
    create_investigation_plan,
    eligible_capabilities,
)
from app.agents.workflow import tenant_workflow, workflow_config
from app.config import settings
from app.domain.bank import (
    evaluate_bank_consistency as evaluate_bank_consistency_evidence,
)
from app.domain.cases import CaseStatus, assert_transition
from app.domain.clarification import build_questions
from app.domain.documents import evaluate_completeness
from app.domain.intelligence import (
    current_sanctions_datasets,
    sanctions_name_score,
    score_duplicate,
)
from app.domain.policy_query import build_supplier_policy_query
from app.domain.provenance import provenance_for
from app.domain.security import canonical_hash, normalize_vendor_name
from app.domain.supplier_controls import evaluate_supplier_controls
from app.llm_gateway import LLMProviderError
from app.models import (
    AgentRun,
    AgentStep,
    ApprovalTask,
    Case,
    ClarificationTask,
    Document,
    DuplicateCandidateRecord,
    ErpOperation,
    EvidenceItem,
    ExtractedField,
    InboxReceipt,
    Notification,
    RiskCheck,
    SanctionsDataset,
    SanctionsEntityRecord,
    Vendor,
)
from app.services.events import append_audit, append_case_event, enqueue_event
from app.services.live_progress import specialist_progress_callback
from app.services.risk import upsert_risk_finding
from app.services.risk_screening import screen_vendor
from app.services.risk_screening import unavailable as risk_screening_unavailable
from app.services.tenant_settings import get_tenant_configuration
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from app.workers.supplier_profile import build_supplier_profile
from langgraph.types import Command
from sqlalchemy import select

# The capability IDs this worker can actually execute.
#
# The registry is a contract: a capability that appears in a plan the operator
# sees, but that nothing runs, tells the operator and the audit trail that a
# check was performed when nothing happened. tests/test_capability_registry.py
# asserts this set matches the registry exactly, so the two cannot drift.
# See plans/91-decisions.md ADR-002.
SUPPLIER_EXECUTORS = frozenset(
    {
        "document_intelligence",
        "duplicate_detection",
        "sanctions_screening",
        "policy_retrieval",
        "bank_consistency",
        "document_completeness",
        "supplier_controls",
        "injection_scan",
        "risk_screening",
    }
)


# Which role owns each control review on a supplier case. Kept beside the
# executor set so adding a review type without deciding who performs it is
# visibly incomplete rather than silently defaulting to procurement.
SUPPLIER_CONTROL_REVIEW_ROLES: dict[str, str] = {
    "SANCTIONS_REVIEW": "compliance_approver",
    "BANK_CHANGE_REVIEW": "finance_approver",
    "PROCUREMENT_REVIEW": "procurement_approver",
    "TAX_REVIEW": "finance_approver",
}


def lexical_score(query: str, content: str) -> float:
    left = {word for word in normalize_vendor_name(query).split() if len(word) > 2}
    right = {word for word in normalize_vendor_name(content).split() if len(word) > 2}
    return len(left & right) / max(1, len(left | right))


async def retrieve_policy(tenant_id: uuid.UUID, query: str) -> tuple[list[dict], str | None]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{settings.RETRIEVAL_URL}/v1/search", json={
                "query": query, "tenant_id": str(tenant_id),
                "roles": ["requester", "analyst", "approver", "auditor", "admin"],
                "effective_date": datetime.now(UTC).date().isoformat(), "limit": 8,
            })
            response.raise_for_status()
            result = response.json()
        return list(result.get("items", [])), None if result.get("status") == "SUCCESS" else "INSUFFICIENT_POLICY_EVIDENCE"
    except Exception:
        return [], "POLICY_RETRIEVAL_UNAVAILABLE"


def duplicate_score(fields: dict[str, str], vendor: Vendor) -> tuple[float, dict]:
    result = score_duplicate(
        legal_name=fields.get("legal_name_normalized", ""),
        tax_id_blind_index=bytes.fromhex(fields["tax_id"]) if fields.get("tax_id") else None,
        bank_account_blind_index=(
            bytes.fromhex(fields["bank_account"]) if fields.get("bank_account") else None
        ),
        country=fields.get("registered_country"),
        email_domain=fields.get("email_domain"),
        candidate_name=vendor.normalized_legal_name,
        candidate_tax_id_blind_index=vendor.tax_id_hash,
        candidate_bank_account_blind_index=vendor.bank_account_hash,
        candidate_country=vendor.registered_country,
        candidate_email_domain=vendor.email_domain,
    )
    return result.score, result.signals


def evaluate_duplicate_candidates(
    fields: dict[str, str],
    vendors: list[Vendor],
) -> list[dict]:
    candidates: list[dict] = []
    for vendor in vendors:
        score, signals = duplicate_score(fields, vendor)
        if score < 0.45:
            continue
        review = score >= 0.70 or bool(
            signals["tax_exact"] or signals["bank_exact"]
        )
        candidates.append(
            {
                "vendor_id": str(vendor.vendor_id),
                "name": vendor.legal_name,
                "score": score,
                "signals": signals,
                "review_required": review,
            }
        )
    return candidates


def evaluate_bank_consistency(fields: dict[str, str]) -> dict:
    """Check the submitted bank evidence against the entity being onboarded.

    The supplier question is whether the bank account is consistent with the
    registered entity and its country - there is no vendor-master row to
    compare against yet, which is what distinguishes this from the invoice
    version of the same capability.
    """
    # SWIFT is deliberately not consulted here. It is stored encrypted, and
    # decrypting it would open a plaintext path through the worker for a
    # fallback the corpus never needs - bank country is stated directly.
    result = evaluate_bank_consistency_evidence(
        legal_name=fields.get("legal_name_plain"),
        beneficiary_name=fields.get("bank_beneficiary_name"),
        registered_country=fields.get("registered_country"),
        bank_country=fields.get("bank_country"),
    )
    return {
        "disposition": result.disposition,
        "signals": result.signals,
        "reason_codes": result.reason_codes,
        "missing_evidence": result.missing_evidence,
    }


def _local_control_step(
    *,
    session,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    attempt: int,
    node_name: str,
    status: str,
    route_reason: str,
    output_summary: dict,
    started_at: datetime,
    started: float,
) -> None:
    session.add(
        AgentStep(
            tenant_id=tenant_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            status=status,
            input_summary={
                "route_reason": route_reason,
                "dependencies": ["document_intelligence"],
                "started_at": started_at.isoformat(),
            },
            output_summary={
                **output_summary,
                "completed_at": datetime.now(UTC).isoformat(),
            },
            error={},
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
    )


def _run_local_controls(
    *,
    session,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    attempt: int,
    profile,
    configuration,
    fields: dict[str, str],
    selected_capabilities: set[str],
    route_reasons: dict[str, str],
) -> dict:
    """Run the deterministic controls and record a step for each.

    Each control emits a real ``AgentStep`` with a measured latency, matching
    the shape of every other step, so a capability the operator sees in the
    plan corresponds to something that visibly ran.
    """
    spend_elevated = (
        profile.annual_spend is not None
        and configuration.spend.is_elevated(profile.annual_spend)
    )

    completeness_started_at = datetime.now(UTC)
    completeness_started = time.perf_counter()
    completeness = evaluate_completeness(
        profile.present_types,
        data_access_declared=bool(profile.data_access_declared),
        data_stored_outside_country=bool(profile.data_stored_outside_country),
        spend_above_threshold=spend_elevated,
        unclassified_count=profile.unclassified_count,
    )
    if "document_completeness" in selected_capabilities:
        _local_control_step(
            session=session,
            tenant_id=tenant_id,
            run_id=run_id,
            attempt=attempt,
            node_name="document_completeness",
            status="SUCCESS" if completeness.disposition == "COMPLETE" else "PARTIAL",
            route_reason=route_reasons.get(
                "document_completeness",
                "The submitted documents must satisfy the required-document matrix.",
            ),
            output_summary={
                "disposition": completeness.disposition,
                "requirements_version": completeness.requirements_version,
                "present": [str(item) for item in completeness.present],
                "missing": [
                    {"document_type": str(item.document_type), "reason": item.reason}
                    for item in completeness.missing
                ],
                "unclassified_count": completeness.unclassified_count,
                "applied_conditions": completeness.applied_conditions,
            },
            started_at=completeness_started_at,
            started=completeness_started,
        )

    controls_started_at = datetime.now(UTC)
    controls_started = time.perf_counter()
    control_result = evaluate_supplier_controls(
        configuration,
        registered_country=fields.get("registered_country"),
        bank_country=fields.get("bank_country"),
        annual_spend=profile.annual_spend,
        spend_currency=profile.spend_currency,
        data_access_declared=profile.data_access_declared,
        data_stored_outside_country=profile.data_stored_outside_country,
        dpa_available=profile.dpa_available,
        dpa_document_present=profile.dpa_document_present,
        insurance_valid_from=profile.insurance_valid_from,
        insurance_valid_to=profile.insurance_valid_to,
        tax_certificate_valid_to=profile.tax_certificate_valid_to,
        as_of=datetime.now(UTC).date(),
    )
    if "supplier_controls" in selected_capabilities:
        _local_control_step(
            session=session,
            tenant_id=tenant_id,
            run_id=run_id,
            attempt=attempt,
            node_name="supplier_controls",
            status=(
                "SUCCESS"
                if control_result.disposition == "CLEAR"
                else "PARTIAL"
            ),
            route_reason=route_reasons.get(
                "supplier_controls",
                "Cross-border, spend, residency, and certificate controls apply to every supplier.",
            ),
            output_summary=control_result.as_dict(),
            started_at=controls_started_at,
            started=controls_started,
        )

    if "injection_scan" in selected_capabilities:
        injection_started_at = datetime.now(UTC)
        injection_started = time.perf_counter()
        _local_control_step(
            session=session,
            tenant_id=tenant_id,
            run_id=run_id,
            attempt=attempt,
            node_name="injection_scan",
            status="PARTIAL" if profile.injection.detected else "SUCCESS",
            route_reason=route_reasons.get(
                "injection_scan",
                "Document content is untrusted and is scanned before any model call.",
            ),
            # The full evidence, including matched spans, is written to the
            # evidence trail for a human. This step summary carries only the
            # shape of what was found.
            output_summary=profile.injection.as_model_safe_summary(),
            started_at=injection_started_at,
            started=injection_started,
        )

    return {
        "completeness": completeness,
        "controls": control_result,
        "spend_elevated": spend_elevated,
    }


def evaluate_sanctions_candidates(
    query_name: str,
    datasets: list[SanctionsDataset],
    sanctions_entities: list[SanctionsEntityRecord],
    missing_sanctions: list[str],
    stale_sanctions: list[str],
) -> tuple[list[dict], str]:
    candidates: list[dict] = []
    datasets_by_id = {dataset.dataset_id: dataset for dataset in datasets}
    for entity in sanctions_entities:
        names = [entity.primary_name, *entity.aliases]
        best_name, best_score = max(
            (
                (name, sanctions_name_score(query_name, name))
                for name in names
            ),
            key=lambda item: item[1],
        )
        if best_score < 0.84:
            continue
        dataset = datasets_by_id[entity.dataset_id]
        candidates.append(
            {
                "source": dataset.source,
                "version": dataset.version,
                "entity_id": entity.external_id,
                "matched_name": best_name,
                "score": round(best_score, 4),
            }
        )
    unavailable = bool(missing_sanctions or stale_sanctions)
    disposition = (
        "UNAVAILABLE"
        if unavailable
        else "POSSIBLE_MATCH"
        if candidates
        else "CLEAR"
    )
    return candidates, disposition


async def handle_case_submitted(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "agent-worker", "event_id": event_id}):
                return
            documents = (await session.execute(select(Document).where(Document.case_id == case_id))).scalars().all()
            if documents and all(document.processing_status == "READY" for document in documents):
                case = await session.get(Case, case_id, with_for_update=True)
                case.status = CaseStatus.SPECIALIST_ANALYSIS
                case.current_version += 1
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case_id,
                    aggregate_version=case.current_version, event_type="agent.analysis.requested.v1",
                    idempotency_key=f"agent.analysis:{case_id}:v{case.current_version}",
                    payload={"case_id": str(case_id), "run_id": str(run_id)},
                )
            else:
                await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="RUN_WAITING_FOR_DOCUMENTS", actor_type="SYSTEM", actor_id="agent-worker", payload={"run_id": str(run_id)})
            session.add(InboxReceipt(consumer_name="agent-worker", event_id=event_id, tenant_id=tenant_id))


async def run_analysis(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "agent-worker", "event_id": event_id}):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if not case or case.tenant_id != tenant_id or not run:
                raise RuntimeError("CASE_OR_RUN_NOT_FOUND")
            run.status = "RUNNING"
            run.current_node = "specialist_analysis"
            run.started_at = run.started_at or datetime.now(UTC)
            await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="SPECIALIST_ANALYSIS_STARTED", actor_type="SYSTEM", actor_id="agent-worker", payload={"run_id": str(run_id)})

            document_started_at = datetime.now(UTC)
            document_started = time.perf_counter()
            fields_rows = (await session.execute(
                select(ExtractedField).join(Document).where(Document.case_id == case_id, ExtractedField.tenant_id == tenant_id)
            )).scalars().all()
            fields: dict[str, str] = {}
            field_sources: dict[str, ExtractedField] = {}
            for field in fields_rows:
                fields[field.field_name] = field.normalized_value or field.field_value_masked or ""
                field_sources[field.field_name] = field
            legal_field = field_sources.get("legal_name")
            legal_name = legal_field.field_value_masked if legal_field else None
            fields["legal_name_normalized"] = normalize_vendor_name(legal_name or "")
            # The legal name is not sensitive, so the masked value is the real
            # one. bank_consistency needs it unnormalized to compare against
            # the beneficiary as written.
            fields["legal_name_plain"] = legal_name or ""
            document_completed_at = datetime.now(UTC)
            session.add(
                AgentStep(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    node_name="document_intelligence",
                    attempt=run.state_version,
                    status="SUCCESS",
                    input_summary={
                        "route_reason": (
                            "Locally extracted supplier evidence is required "
                            "before identity and policy investigation."
                        ),
                        "dependencies": ["document_processing"],
                        "started_at": document_started_at.isoformat(),
                    },
                    output_summary={
                        "field_count": len(fields_rows),
                        "document_count": len(
                            {
                                field.document_id
                                for field in fields_rows
                            }
                        ),
                        "completed_at": (
                            document_completed_at.isoformat()
                        ),
                    },
                    error={},
                    latency_ms=round(
                        (time.perf_counter() - document_started) * 1000
                    ),
                )
            )

            # Document classification, questionnaire answers, certificate
            # dates, and the injection scan all come from one pass over the
            # case's documents, keeping each fact tied to the document that
            # stated it.
            profile = await build_supplier_profile(session, tenant_id, case_id)
            configuration = await get_tenant_configuration(session, tenant_id)

            observable_facts = {
                "documents_ready": True,
                "legal_name_available": bool(fields["legal_name_normalized"]),
                "bank_account_available": bool(fields.get("bank_account")),
                "registered_country_available": bool(
                    fields.get("registered_country")
                ),
            }
            planner_error: LLMProviderError | None = None
            plan = None
            try:
                plan = await create_investigation_plan(
                    "supplier",
                    "Investigate this supplier and prepare a safe, evidence-backed onboarding decision.",
                    observable_facts,
                )
                selected_capabilities = {
                    item.capability_id
                    for item in plan.output.selected_capabilities
                }
                session.add(
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name="goal_planner",
                        attempt=run.state_version,
                        status="SUCCESS",
                        input_summary={
                            "observable_facts": observable_facts,
                            "route_reason": (
                                "The high-level supplier onboarding goal "
                                "requires a validated investigation plan."
                            ),
                            "dependencies": [],
                        },
                        output_summary={
                            "plan": plan.as_dict(),
                            "provider_version": plan.model_version,
                        },
                        error={},
                        latency_ms=plan.latency_ms,
                    )
                )
            except LLMProviderError as exc:
                planner_error = exc
                selected_capabilities = {
                    capability.capability_id
                    for capability in eligible_capabilities(
                        "supplier",
                        observable_facts,
                    )
                    if capability.mandatory_when_eligible
                }
                session.add(
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name="goal_planner",
                        attempt=run.state_version,
                        status="FAILED",
                        input_summary={
                            "observable_facts": observable_facts,
                            "route_reason": (
                                "The high-level supplier onboarding goal "
                                "requires a validated investigation plan."
                            ),
                            "dependencies": [],
                        },
                        output_summary={
                            "preserved_mandatory_work": sorted(
                                selected_capabilities
                            )
                        },
                        error={
                            "error_code": exc.error_code,
                            "retryable": exc.retryable,
                            "upgrade_required": exc.upgrade_required,
                        },
                        latency_ms=None,
                    )
                )

            vendors = (
                await session.execute(
                    select(Vendor).where(Vendor.tenant_id == tenant_id)
                )
            ).scalars().all()

            published_datasets = (
                await session.execute(
                    select(SanctionsDataset).where(
                        SanctionsDataset.status == "PUBLISHED"
                    )
                )
            ).scalars().all()
            datasets, missing_sanctions, stale_sanctions = (
                current_sanctions_datasets(
                    list(published_datasets),
                    max_age_hours=settings.SANCTIONS_MAX_AGE_HOURS,
                )
            )
            dataset_ids = [dataset.dataset_id for dataset in datasets]
            sanctions_entities = (await session.execute(
                select(SanctionsEntityRecord).where(SanctionsEntityRecord.dataset_id.in_(dataset_ids))
            )).scalars().all() if dataset_ids else []

            # Local, deterministic controls run first and synchronously. They
            # are pure functions over already-extracted evidence, so there is
            # nothing to parallelise - and the policy query is composed from
            # their findings, which means they must be finished before
            # retrieval starts. See app/domain/policy_query.py.
            local_controls = _run_local_controls(
                session=session,
                tenant_id=tenant_id,
                run_id=run_id,
                attempt=run.state_version,
                profile=profile,
                configuration=configuration,
                fields=fields,
                selected_capabilities=selected_capabilities,
                route_reasons=(
                    {
                        item.capability_id: item.rationale
                        for item in plan.output.selected_capabilities
                    }
                    if plan
                    else {}
                ),
            )
            completeness = local_controls["completeness"]
            control_result = local_controls["controls"]
            injection = profile.injection

            policy_query_plan = build_supplier_policy_query(
                reason_codes=[
                    *completeness.reason_codes,
                    *control_result.reason_codes,
                    *injection.reason_codes,
                ],
                registered_country=fields.get("registered_country"),
                bank_country=fields.get("bank_country"),
                data_access_declared=bool(profile.data_access_declared),
                spend_elevated=(
                    profile.annual_spend is not None
                    and configuration.spend.is_elevated(profile.annual_spend)
                ),
            )
            policy_query = policy_query_plan.text

            selected_operations = {}
            if "duplicate_detection" in selected_capabilities:
                selected_operations["duplicate_detection"] = (
                    asyncio.to_thread(
                        evaluate_duplicate_candidates,
                        fields,
                        list(vendors),
                    )
                )
            if "sanctions_screening" in selected_capabilities:
                selected_operations["sanctions_screening"] = (
                    asyncio.to_thread(
                        evaluate_sanctions_candidates,
                        fields["legal_name_normalized"],
                        list(datasets),
                        list(sanctions_entities),
                        missing_sanctions,
                        stale_sanctions,
                    )
                )
            if "policy_retrieval" in selected_capabilities:
                selected_operations["policy_retrieval"] = (
                    retrieve_policy(tenant_id, policy_query)
                )
            if "bank_consistency" in selected_capabilities:
                selected_operations["bank_consistency"] = asyncio.to_thread(
                    evaluate_bank_consistency,
                    fields,
                )
            if "risk_screening" in selected_capabilities:
                selected_operations["risk_screening"] = screen_vendor(
                    fields.get("legal_name_plain", "")
                )
            route_reasons = {
                item.capability_id: item.rationale
                for item in plan.output.selected_capabilities
            } if plan else {}
            specialist_dependencies = {
                capability_id: (
                    ["document_intelligence"]
                    if capability_id
                    in {
                        "duplicate_detection",
                        "sanctions_screening",
                        "bank_consistency",
                        "risk_screening",
                    }
                    else ["goal_planner"]
                )
                for capability_id in selected_operations
            }
            specialist_results = await execute_parallel(
                selected_operations,
                on_progress=specialist_progress_callback(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    attempt=run.state_version,
                    route_reasons=route_reasons,
                    dependencies=specialist_dependencies,
                ),
            )
            duplicate_result = specialist_results.get(
                "duplicate_detection"
            )
            duplicate_items = (
                duplicate_result["result"]
                if duplicate_result
                and duplicate_result["status"] == "SUCCESS"
                else []
            )
            sanctions_result = specialist_results.get(
                "sanctions_screening"
            )
            risk_candidates, risk_disposition = (
                sanctions_result["result"]
                if sanctions_result
                and sanctions_result["status"] == "SUCCESS"
                else ([], "UNAVAILABLE")
            )
            policy_result = specialist_results.get("policy_retrieval")
            policy_items, policy_error = (
                policy_result["result"]
                if policy_result
                and policy_result["status"] == "SUCCESS"
                else ([], "POLICY_RETRIEVAL_UNAVAILABLE")
            )
            bank_result = specialist_results.get("bank_consistency")
            bank_evidence = (
                bank_result["result"]
                if bank_result and bank_result["status"] == "SUCCESS"
                else None
            )
            screening_result = specialist_results.get("risk_screening")
            screening = (
                screening_result["result"]
                if screening_result and screening_result["status"] == "SUCCESS"
                # A raised exception is itself an outage. Fail closed rather
                # than letting an absent result read as a clean one.
                else risk_screening_unavailable("RISK_SERVICE_CALL_FAILED")
                if screening_result
                else None
            )

            specialist_summaries = {
                "duplicate_detection": {
                    "candidate_count": len(duplicate_items),
                    "review_required": any(
                        item["review_required"]
                        for item in duplicate_items
                    ),
                },
                "sanctions_screening": {
                    "candidate_count": len(risk_candidates),
                    "disposition": risk_disposition,
                    "dataset_versions": {
                        item.source: item.version for item in datasets
                    },
                },
                "policy_retrieval": {
                    "clause_count": len(policy_items),
                    "status": (
                        "SUCCESS" if policy_items else "BLOCKED"
                    ),
                    "error_code": policy_error,
                },
                "bank_consistency": {
                    "disposition": (
                        bank_evidence["disposition"]
                        if bank_evidence
                        else "UNVERIFIED"
                    ),
                    "signals": bank_evidence["signals"] if bank_evidence else {},
                    "missing_evidence": (
                        bank_evidence["missing_evidence"] if bank_evidence else []
                    ),
                },
                "risk_screening": (
                    screening.as_dict()
                    if screening
                    else {"disposition": "NOT_SELECTED"}
                ),
            }
            for capability_id, result in specialist_results.items():
                summary = specialist_summaries[capability_id]
                blocked = (
                    capability_id == "sanctions_screening"
                    and risk_disposition == "UNAVAILABLE"
                ) or (
                    capability_id == "policy_retrieval"
                    and not policy_items
                ) or (
                    # An unavailable risk provider is a blocked check, not a
                    # passing one. Making that visible on the step is the whole
                    # reason the fixture ships an UNAVAILABLE vendor.
                    capability_id == "risk_screening"
                    and screening is not None
                    and screening.disposition == "UNAVAILABLE"
                )
                status = (
                    "FAILED"
                    if result["status"] == "FAILED"
                    else "BLOCKED"
                    if blocked
                    else "PARTIAL"
                    # Absent bank evidence is not a clean bank check. Reporting
                    # SUCCESS here would tell the operator the account was
                    # verified when nothing was compared.
                    if capability_id == "bank_consistency"
                    and summary["disposition"] == "UNVERIFIED"
                    else "SUCCESS"
                )
                session.add(
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name=capability_id,
                        attempt=run.state_version,
                        status=status,
                        input_summary={
                            "route_reason": route_reasons.get(
                                capability_id,
                                "Mandatory safety investigation retained after planner failure.",
                            ),
                            "dependencies": specialist_dependencies[
                                capability_id
                            ],
                            "started_at": result[
                                "started_at"
                            ].isoformat(),
                        },
                        output_summary={
                            **summary,
                            "completed_at": result[
                                "completed_at"
                            ].isoformat(),
                        },
                        error=(
                            result["error"]
                            if result["status"] == "FAILED"
                            else {
                                "error_code": summary.get("error_code"),
                                "retryable": (
                                    capability_id == "policy_retrieval"
                                    and not policy_items
                                ),
                            }
                        ),
                        latency_ms=result["latency_ms"],
                    )
                )

            for item in duplicate_items:
                session.add(DuplicateCandidateRecord(
                    tenant_id=tenant_id, case_id=case_id,
                    vendor_id=uuid.UUID(item["vendor_id"]),
                    score=item["score"], signals=item["signals"],
                    review_required=item["review_required"],
                ))
            review_candidates = [
                item for item in duplicate_items if item["review_required"]
            ]
            if review_candidates:
                strongest = max(
                    review_candidates, key=lambda item: item["score"]
                )
                await upsert_risk_finding(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    subject_type="VENDOR",
                    subject_id=strongest["vendor_id"],
                    finding_type="DUPLICATE_VENDOR",
                    severity="HIGH",
                    mode="ACTIVE",
                    detector_key="vendor_entity_resolution",
                    detector_version="2.0.0",
                    score=float(strongest["score"]),
                    threshold=0.70,
                    reason_codes=["POSSIBLE_DUPLICATE"],
                    feature_snapshot=strongest["signals"],
                    explanation={
                        "summary": (
                            "Candidate generation uses normalized fuzzy name "
                            "matching; exact tax or bank blind-index matches "
                            "always require human review."
                        )
                    },
                    evidence_refs=[
                        {
                            "source_type": "VENDOR_MASTER",
                            "vendor_id": strongest["vendor_id"],
                        }
                    ],
                )
            if bank_evidence and bank_evidence["disposition"] == "MISMATCH":
                await upsert_risk_finding(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    subject_type="CASE",
                    subject_id=str(case_id),
                    finding_type="BANK_EVIDENCE_INCONSISTENT",
                    severity="HIGH",
                    mode="ACTIVE",
                    detector_key="supplier_bank_consistency",
                    detector_version="1.0.0",
                    score=1.0,
                    threshold=1.0,
                    reason_codes=bank_evidence["reason_codes"],
                    feature_snapshot=bank_evidence["signals"],
                    explanation={
                        "summary": (
                            "The submitted bank evidence does not agree with "
                            "the entity being onboarded. A payment instruction "
                            "that names a different party, or a bank in a "
                            "different jurisdiction to the registered entity, "
                            "requires independent verification before any "
                            "vendor record is created."
                        )
                    },
                    evidence_refs=[
                        {
                            "source_type": "EXTRACTED_FIELD",
                            "field_name": name,
                        }
                        for name in (
                            "legal_name",
                            "bank_beneficiary_name",
                            "registered_country",
                            "bank_country",
                        )
                        if name in field_sources
                    ],
                )
            if injection.detected:
                await upsert_risk_finding(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    subject_type="CASE",
                    subject_id=str(case_id),
                    finding_type="UNTRUSTED_DOCUMENT_INSTRUCTION",
                    severity="HIGH",
                    mode="ACTIVE",
                    detector_key="deterministic_injection_scan",
                    detector_version="1.0.0",
                    score=1.0,
                    threshold=1.0,
                    reason_codes=injection.reason_codes,
                    feature_snapshot={"pattern_ids": injection.pattern_ids},
                    explanation={
                        "summary": (
                            "A submitted document contains text addressed to "
                            "the processing system, attempting to bypass "
                            "approval requirements. The instruction was "
                            "detected before any model call and was not acted "
                            "on. The document may still be legitimate, so the "
                            "case is routed for clarification rather than "
                            "rejected."
                        )
                    },
                    evidence_refs=[
                        {
                            "source_type": "DOCUMENT_PAGE",
                            "page": match.page,
                            "pattern_id": match.pattern_id,
                        }
                        for match in injection.matches
                    ],
                )
            for finding in control_result.findings:
                if not finding.needs_attention or not finding.reason_code:
                    continue
                await upsert_risk_finding(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    subject_type="CASE",
                    subject_id=str(case_id),
                    finding_type=finding.reason_code,
                    severity="HIGH",
                    mode="ACTIVE",
                    detector_key=f"supplier_control:{finding.control}",
                    detector_version="1.0.0",
                    score=1.0,
                    threshold=1.0,
                    reason_codes=[finding.reason_code],
                    feature_snapshot=dict(finding.evidence),
                    explanation={"summary": finding.summary},
                    evidence_refs=[
                        {"source_type": "EXTRACTED_FIELD", "control": finding.control}
                    ],
                )
            if screening and screening.disposition != "CLEAR":
                await upsert_risk_finding(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    subject_type="CASE",
                    subject_id=str(case_id),
                    finding_type=(
                        "RISK_SERVICE_UNAVAILABLE"
                        if screening.disposition == "UNAVAILABLE"
                        else "EXTERNAL_RISK_MATCH"
                    ),
                    severity="HIGH",
                    mode="ACTIVE",
                    detector_key="external_risk_screening",
                    detector_version="1.0.0",
                    score=1.0,
                    threshold=1.0,
                    reason_codes=screening.reason_codes,
                    feature_snapshot=screening.as_dict(),
                    explanation={
                        "summary": (
                            "The external risk provider did not return a "
                            "usable result, so screening is incomplete. An "
                            "unavailable check is not a passed check."
                            if screening.disposition == "UNAVAILABLE"
                            else "External screening returned a signal that "
                            "requires human review before onboarding."
                        )
                    },
                    evidence_refs=[
                        {
                            "source_type": "RISK_SERVICE",
                            "checked_at": screening.checked_at,
                        }
                    ],
                )
            session.add(RiskCheck(
                tenant_id=tenant_id, case_id=case_id, provider="LOCAL_OFFICIAL_LISTS",
                dataset_versions={item.source: item.version for item in datasets},
                status="BLOCKED" if risk_disposition == "UNAVAILABLE" else "SUCCESS",
                disposition=risk_disposition,
                result={
                    "candidates": risk_candidates,
                    "missing_sources": missing_sanctions,
                    "stale_sources": stale_sanctions,
                },
            ))

            unresolved = []
            if not legal_name:
                unresolved.append("legal_name")
            low_confidence_fields = [
                (field.field_name, field.source_page)
                for field in fields_rows
                if field.field_name in {"tax_id", "bank_account"}
                and not field.human_verified
                and (field.confidence or 0) < 0.90
            ]
            unresolved.extend(name for name, _ in low_confidence_fields)
            # A missing required document is deliberately *not* added to
            # unresolved. Doing so would force every such case to clarification
            # and hide the risk findings underneath - VO-003 omits its tax
            # certificate and still expects an enhanced review driven by its
            # cross-border, residency, and expiry findings. The missing
            # document contributes a reason code and a clarification question,
            # and the routing rules below decide what wins.
            blockers = []
            if (
                duplicate_result
                and duplicate_result["status"] == "FAILED"
            ):
                blockers.append("DUPLICATE_DETECTION_FAILED")
            if risk_disposition == "UNAVAILABLE":
                blockers.append("SANCTIONS_DATA_UNAVAILABLE")
            if not policy_items:
                blockers.append(policy_error or "INSUFFICIENT_POLICY_EVIDENCE")
            if planner_error:
                blockers.append(planner_error.error_code)
            reason_codes = list(blockers)
            if any(item["review_required"] for item in duplicate_items):
                reason_codes.append("POSSIBLE_DUPLICATE")
            if risk_disposition == "POSSIBLE_MATCH":
                reason_codes.append("SANCTIONS_REVIEW_REQUIRED")
            if bank_evidence:
                # A mismatch is a finding for a human, not a workflow failure -
                # which is why the registry declares this capability RETRYABLE
                # for suppliers and BLOCKING for invoices.
                reason_codes.extend(bank_evidence["reason_codes"])
            reason_codes.extend(completeness.reason_codes)
            reason_codes.extend(control_result.reason_codes)
            reason_codes.extend(injection.reason_codes)
            if screening:
                reason_codes.extend(screening.reason_codes)
            reason_codes = list(dict.fromkeys(reason_codes))

            control_evidence = {
                finding.reason_code: finding.evidence
                for finding in control_result.findings
                if finding.reason_code
            }
            clarification_questions = build_questions(
                completeness=completeness,
                control_reason_codes=[
                    *control_result.reason_codes,
                    *(bank_evidence["reason_codes"] if bank_evidence else []),
                    *injection.reason_codes,
                    *(screening.reason_codes if screening else []),
                ],
                control_evidence={
                    **control_evidence,
                    **(
                        {
                            code: bank_evidence["signals"]
                            for code in bank_evidence["reason_codes"]
                        }
                        if bank_evidence
                        else {}
                    ),
                },
                low_confidence_fields=low_confidence_fields,
                missing_fields=["legal_name"] if not legal_name else [],
            )

            recommendation = "REQUEST_INFORMATION" if unresolved else "REVIEW_REQUIRED" if reason_codes else "CREATE_VENDOR"
            packet = {
                "case_id": str(case_id), "run_id": str(run_id), "recommendation": recommendation,
                "reason_codes": reason_codes,
                "vendor": {
                    "legal_name": legal_name,
                    "registered_country": fields.get("registered_country"),
                    "email_domain": fields.get("email_domain"),
                },
                "duplicate_candidates": duplicate_items, "risk": {"disposition": risk_disposition, "candidates": risk_candidates},
                "policy_clauses": policy_items, "unresolved_items": sorted(set(unresolved)),
                "bank_consistency": bank_evidence,
                "document_completeness": {
                    "disposition": completeness.disposition,
                    "requirements_version": completeness.requirements_version,
                    "missing": [
                        {
                            "document_type": str(item.document_type),
                            "label": item.label,
                            "reason": item.reason,
                        }
                        for item in completeness.missing
                    ],
                },
                "supplier_controls": control_result.as_dict(),
                # The full injection evidence, matched spans included, is for
                # the human reviewer. It never enters a model payload.
                "untrusted_instructions": injection.as_evidence(),
                "risk_screening": screening.as_dict() if screening else None,
                "policy_query": policy_query_plan.as_dict(),
                "supplier_profile": profile.as_dict(),
                "clarification_questions": [
                    question.as_dict() for question in clarification_questions
                ],
            }
            evidence_hash = canonical_hash(packet)
            evidence_rows: list[EvidenceItem] = []
            for item in policy_items:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="POLICY",
                    provenance=provenance_for("POLICY"),
                    source_id=f"{item['policy_code']}:{item['version']}:{item['clause_id']}",
                    source_locator={"effective_date": item["effective_date"]}, claim=item["content"],
                    reason_code="POLICY_CLAUSE", confidence=item.get("rerank_score"),
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            for item in duplicate_items:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="VENDOR_MASTER",
                    provenance=provenance_for("VENDOR_MASTER"),
                    source_id=item["vendor_id"], source_locator={"signals": item["signals"]},
                    claim=f"Potential duplicate: {item['name']}", reason_code="DUPLICATE_SCORE", confidence=item["score"],
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            if bank_evidence:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    source_type="EXTRACTED_FIELD",
                    # The bank evidence comes from documents the supplier
                    # supplied, so it is self-asserted. Recording that is what
                    # keeps a beneficiary mismatch a question for a human
                    # rather than something the system resolves on its own.
                    provenance=provenance_for("EXTRACTED_FIELD"),
                    source_id="bank_consistency",
                    source_locator={"signals": bank_evidence["signals"]},
                    claim=(
                        "Bank evidence disposition: "
                        f"{bank_evidence['disposition']}"
                    ),
                    reason_code="BANK_CONSISTENCY",
                    confidence=None,
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            if screening:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    source_type="RISK_SERVICE",
                    provenance=provenance_for("RISK_SERVICE"),
                    source_id=screening.matched_name,
                    source_locator={"checked_at": screening.checked_at},
                    claim=(
                        f"External risk screening: {screening.disposition}"
                        + (
                            f" (adverse media: {screening.adverse_media})"
                            if screening.adverse_media
                            else ""
                        )
                    ),
                    reason_code="EXTERNAL_RISK_SCREENING",
                    confidence=None,
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            if injection.detected:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    source_type="DOCUMENT_PAGE",
                    provenance=provenance_for("DOCUMENT_PAGE"),
                    source_id="injection_scan",
                    # The matched spans live here, for the reviewer. This
                    # record is never included in a model payload.
                    source_locator=injection.as_evidence(),
                    claim=(
                        "A submitted document contains an instruction "
                        "attempting to override workflow controls. It was "
                        "detected before any model call and was not acted on."
                    ),
                    reason_code="UNTRUSTED_DOCUMENT_INSTRUCTION",
                    confidence=None,
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            await session.flush()

            graph_packet = {
                "_data_classification": settings.LLM_DATA_CLASSIFICATION,
                "recommendation": recommendation,
                "reason_codes": reason_codes,
                "unresolved_items": sorted(set(unresolved)),
                "deterministic_checks": {
                    "duplicate": (
                        "REVIEW_REQUIRED"
                        if any(item["review_required"] for item in duplicate_items)
                        else "CLEAR"
                    ),
                    "sanctions": risk_disposition,
                    "policy": "SUFFICIENT" if policy_items else "INSUFFICIENT",
                    "bank_consistency": (
                        bank_evidence["disposition"]
                        if bank_evidence
                        else "NOT_SELECTED"
                    ),
                    "document_completeness": completeness.disposition,
                    "supplier_controls": control_result.disposition,
                    "external_risk": (
                        screening.disposition if screening else "NOT_SELECTED"
                    ),
                    # Only the shape reaches the model, never the matched text.
                    # Handing an injection attempt to the model "for context"
                    # gives it exactly the delivery it was after.
                    "untrusted_document_instruction": (
                        injection.as_model_safe_summary()
                    ),
                },
                "evidence": [
                    {
                        "evidence_id": str(evidence.evidence_item_id),
                        "source_type": evidence.source_type,
                        "reason_code": evidence.reason_code,
                        "tokenized_claim": (
                            evidence.claim
                            if evidence.source_type == "POLICY"
                            else "A deterministic vendor-master match requires review."
                        ),
                    }
                    for evidence in evidence_rows
                ],
                "policy_citations": [
                    f"{item['policy_code']}:{item['version']}:{item['clause_id']}"
                    for item in policy_items
                ],
                "packet_hash": evidence_hash,
            }
            graph_state = {
                "tenant_id": str(tenant_id),
                "case_id": str(case_id),
                "run_id": str(run_id),
                "workflow_kind": "supplier",
                "evidence_hash": evidence_hash,
                "case_version": case.current_version + 1,
                "human_gate_kind": (
                    "CLARIFICATION" if unresolved else "APPROVAL"
                ),
                # De-duplicated: the workflow consumes this list by index, so
                # two entries of the same type would demand the same review
                # twice. Sanctions and the external risk provider can both
                # raise a compliance review, and one is enough.
                "required_reviews": list(dict.fromkeys(
                    review_type
                    for review_type, required in (
                        (
                            "DUPLICATE_REVIEW",
                            any(
                                item["review_required"]
                                for item in duplicate_items
                            ),
                        ),
                        (
                            "SANCTIONS_REVIEW",
                            risk_disposition == "POSSIBLE_MATCH",
                        ),
                        (
                            "BANK_CHANGE_REVIEW",
                            bool(
                                bank_evidence
                                and bank_evidence["disposition"] == "MISMATCH"
                            ),
                        ),
                        (
                            # Cross-border banking, elevated spend, data
                            # residency, an unavailable DPA, an expired
                            # certificate, or a missing required document.
                            # Any of these makes the case an enhanced review.
                            "PROCUREMENT_REVIEW",
                            bool(
                                control_result.reason_codes
                                or completeness.missing
                            ),
                        ),
                        (
                            "SANCTIONS_REVIEW",
                            bool(screening and screening.disposition != "CLEAR"),
                        ),
                    )
                    if required
                )),
                "completed_reviews": [],
                "deterministic_packet": graph_packet,
                "current_stage": "deterministic_checks_complete",
            }
            if planner_error:
                graph_result = {
                    **graph_state,
                    "current_stage": "goal_planner_blocked",
                    "outcome": "BLOCKED",
                    "blocker": {
                        "error_code": planner_error.error_code,
                        "retryable": planner_error.retryable,
                        "upgrade_required": planner_error.upgrade_required,
                    },
                }
            else:
                async with tenant_workflow(str(tenant_id)) as graph:
                    graph_result = await graph.ainvoke(
                        graph_state,
                        workflow_config(run.thread_id),
                    )

            for node_name, result_key in (
                ("gemini_contradiction", "contradiction_result"),
                ("deterministic_verification", "verification_result"),
                ("gemini_evidence_critique", "critique_result"),
            ):
                result = graph_result.get(result_key)
                if not result:
                    continue
                session.add(
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name=node_name,
                        attempt=run.state_version,
                        status=result["status"],
                        input_summary={
                            "evidence_hash": evidence_hash,
                            "reason_code_count": len(reason_codes),
                        },
                        output_summary={
                            "data": result.get("data", {}),
                            "provider_version": result["provider_version"],
                            "idempotency_key": result["idempotency_key"],
                        },
                        error={
                            "error_code": result.get("error_code"),
                            "retryable": result.get("retryable", False),
                        },
                        latency_ms=result["latency_ms"],
                    )
                )

            case.current_version += 1
            if graph_result.get("blocker"):
                blocker = graph_result["blocker"]
                case.status = CaseStatus.VERIFICATION_FAILED
                run.status = "BLOCKED"
                run.current_node = graph_result["current_stage"]
                await append_case_event(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    event_type="AGENT_BLOCKED",
                    actor_type="SYSTEM",
                    actor_id="agent-worker",
                    payload={
                        "run_id": str(run_id),
                        "error_code": blocker["error_code"],
                        "retryable": blocker["retryable"],
                        "upgrade_required": blocker.get(
                            "upgrade_required",
                            False,
                        ),
                    },
                )
            elif unresolved:
                case.status = CaseStatus.NEEDS_CLARIFICATION
                task = ClarificationTask(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    # Questions come from the deterministic findings above, so
                    # each one names the specific document, field, or control
                    # that produced it. A generic "please confirm or provide
                    # legal name" is not actionable for a case blocked on an
                    # expired certificate or a cross-border bank account.
                    questions=[
                        question.as_dict() for question in clarification_questions
                    ]
                    or [
                        {
                            "field": item,
                            "question": (
                                f"Please confirm or provide {item.replace('_', ' ')}."
                            ),
                            "reason_code": "FIELD_NOT_STATED",
                            "locator": {},
                        }
                        for item in sorted(set(unresolved))
                    ],
                )
                session.add(task)
                await session.flush()
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="clarification", aggregate_id=task.clarification_task_id,
                    aggregate_version=1, event_type="clarification.requested.v1",
                    idempotency_key=f"clarification.request:{run_id}:v{case.current_version}",
                    payload={"case_id": str(case_id), "run_id": str(run_id), "clarification_task_id": str(task.clarification_task_id)},
                )
                run.status = "INTERRUPTED"
                run.current_node = "clarification"
            elif blockers:
                case.status = CaseStatus.VERIFICATION_FAILED
                run.status = "INTERRUPTED"
                run.current_node = "verification_failed"
            else:
                interrupt_value = graph_result["__interrupt__"][0].value
                task_type = (
                    interrupt_value["review_type"]
                    if interrupt_value["kind"] == "CONTROL_REVIEW"
                    else "VENDOR_CREATION"
                )
                if task_type == "DUPLICATE_REVIEW":
                    case.status = CaseStatus.DUPLICATE_REVIEW
                    assigned_role = "procurement_approver"
                elif task_type in SUPPLIER_CONTROL_REVIEW_ROLES:
                    case.status = CaseStatus.RISK_REVIEW
                    assigned_role = SUPPLIER_CONTROL_REVIEW_ROLES[task_type]
                else:
                    case.status = CaseStatus.APPROVAL_PENDING
                    assigned_role = "procurement_approver"
                task = ApprovalTask(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    task_type=task_type,
                    assigned_role=assigned_role,
                    proposed_action={
                        "action": (
                            "CREATE_VENDOR"
                            if task_type == "VENDOR_CREATION"
                            else "RESOLVE_CONTROL_REVIEW"
                        ),
                        "payload": packet["vendor"],
                    },
                    evidence_packet=packet, evidence_hash=evidence_hash, case_version=case.current_version,
                )
                session.add(task)
                run.status = "INTERRUPTED"
                run.current_node = (
                    "control_review"
                    if interrupt_value["kind"] == "CONTROL_REVIEW"
                    else "approval_interrupt"
                )
                notification = Notification(
                    tenant_id=tenant_id, case_id=case_id, notification_type="APPROVAL_REQUIRED",
                    title=f"Approval required: {case.case_number}", body="A verified vendor evidence packet is ready for review.",
                )
                session.add(notification)
                await session.flush()
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="notification", aggregate_id=notification.notification_id,
                    aggregate_version=1, event_type="notification.delivery.requested.v1",
                    idempotency_key=f"notification.delivery:{notification.notification_id}:1",
                    payload={"notification_id": str(notification.notification_id), "target_role": task.assigned_role, "attempt": 1},
                )
                enqueue_event(
                    session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case_id,
                    aggregate_version=case.current_version, event_type="approval.requested.v1",
                    idempotency_key=f"approval.request:{run_id}:{evidence_hash}",
                    payload={"case_id": str(case_id), "run_id": str(run_id), "evidence_hash": evidence_hash},
                )
            run.state_json = {
                "evidence_hash": evidence_hash,
                "plan": plan.as_dict() if plan else {
                    "status": "FAILED",
                    "error_code": planner_error.error_code
                    if planner_error
                    else "UNKNOWN",
                    "preserved_mandatory_work": sorted(
                        selected_capabilities
                    ),
                },
                "recommendation": recommendation,
                "reason_codes": reason_codes,
                "unresolved_items": unresolved,
                "current_stage": graph_result["current_stage"],
                "blocker": graph_result.get("blocker"),
                "contradiction_result": graph_result.get(
                    "contradiction_result"
                ),
                "verification_result": graph_result.get(
                    "verification_result"
                ),
                "critique_result": graph_result.get("critique_result"),
            }
            run.model_name = settings.DEFAULT_MODEL
            run.prompt_version = "enterprise-evidence-v1"
            run.input_hash = evidence_hash
            run.state_version += 1
            await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ANALYSIS_COMPLETED", actor_type="SYSTEM", actor_id="agent-worker", payload={"run_id": str(run_id), "status": case.status, "recommendation": recommendation, "reason_codes": reason_codes})
            await append_audit(session, tenant_id=tenant_id, case_id=case_id, actor_type="SYSTEM", actor_id="agent-worker", action="ANALYSIS_COMPLETED", resource_type="AGENT_RUN", resource_id=str(run_id), metadata={"evidence_hash": evidence_hash, "reason_codes": reason_codes})
            session.add(InboxReceipt(consumer_name="agent-worker", event_id=event_id, tenant_id=tenant_id))


async def resume_human_decision(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    payload = envelope["payload"]
    case_id = uuid.UUID(payload["case_id"])
    run_id = uuid.UUID(payload["run_id"])
    task_id = uuid.UUID(payload["task_id"])
    decision = payload["decision"]
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(
                InboxReceipt,
                {"consumer_name": "agent-worker", "event_id": event_id},
            ):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            task = (
                await session.get(ClarificationTask, task_id)
                if decision == "CLARIFIED"
                else await session.get(ApprovalTask, task_id)
            )
            if (
                not case
                or case.tenant_id != tenant_id
                or not run
                or not task
                or task.run_id != run_id
            ):
                raise RuntimeError("WORKFLOW_RESUME_CONTEXT_NOT_FOUND")
            if decision == "ESCALATED":
                session.add(
                    InboxReceipt(
                        consumer_name="agent-worker",
                        event_id=event_id,
                        tenant_id=tenant_id,
                    )
                )
                return
            async with tenant_workflow(str(tenant_id)) as graph:
                result = await graph.ainvoke(
                    Command(
                        resume={
                            "decision": decision,
                            "task_id": str(task_id),
                            "evidence_hash": payload["evidence_hash"],
                            "expected_version": payload["expected_version"],
                            "actor_id": payload["actor_id"],
                        }
                    ),
                    workflow_config(run.thread_id),
                )
            interrupts = result.get("__interrupt__", ())
            if interrupts:
                interrupt_value = interrupts[0].value
                interrupt_kind = interrupt_value.get("kind")
                if interrupt_kind == "ERP_CONFIRMATION":
                    if case.status != CaseStatus.APPROVED:
                        raise RuntimeError("ERP_REQUIRES_APPROVED_CASE")
                    assert_transition(case.status, CaseStatus.ERP_SYNC_PENDING)
                    case.status = CaseStatus.ERP_SYNC_PENDING
                    case.current_version += 1
                    erp_event = (
                        "invoice.resolution.approved.v1"
                        if case.case_type == "INVOICE_EXCEPTION"
                        else "erp.sync.requested.v1"
                    )
                    enqueue_event(
                        session,
                        tenant_id=tenant_id,
                        aggregate_type="case",
                        aggregate_id=case_id,
                        aggregate_version=case.current_version,
                        event_type=erp_event,
                        idempotency_key=interrupt_value["idempotency_key"],
                        payload={
                            "case_id": str(case_id),
                            "run_id": str(run_id),
                            "approval_task_id": str(task_id),
                            "evidence_hash": payload["evidence_hash"],
                        },
                    )
                    run.current_node = "erp_confirmation"
                    await append_case_event(
                        session,
                        tenant_id=tenant_id,
                        case_id=case_id,
                        event_type="ERP_SYNC_QUEUED",
                        actor_type="SYSTEM",
                        actor_id="agent-worker",
                        payload={
                            "run_id": str(run_id),
                            "status": case.status,
                        },
                    )
                elif interrupt_kind in {"CONTROL_REVIEW", "APPROVAL"}:
                    if interrupt_kind == "CONTROL_REVIEW":
                        next_task_type = interrupt_value["review_type"]
                        assigned_role = {
                            "DUPLICATE_REVIEW": "procurement_approver",
                            "SANCTIONS_REVIEW": "compliance_approver",
                            "BANK_CHANGE_REVIEW": "finance_approver",
                            "TAX_REVIEW": "finance_approver",
                            "PROCUREMENT_REVIEW": "procurement_approver",
                        }[next_task_type]
                        if case.case_type == "INVOICE_EXCEPTION":
                            target = (
                                CaseStatus.BLOCKED_DUPLICATE
                                if next_task_type == "DUPLICATE_REVIEW"
                                else CaseStatus.HOLD
                            )
                        else:
                            target = (
                                CaseStatus.DUPLICATE_REVIEW
                                if next_task_type == "DUPLICATE_REVIEW"
                                else CaseStatus.RISK_REVIEW
                            )
                    else:
                        next_task_type = (
                            "INVOICE_AP_APPROVAL"
                            if case.case_type == "INVOICE_EXCEPTION"
                            else "VENDOR_CREATION"
                        )
                        assigned_role = (
                            "finance_approver"
                            if case.case_type == "INVOICE_EXCEPTION"
                            else "procurement_approver"
                        )
                        target = CaseStatus.APPROVAL_PENDING
                    if case.status != target:
                        assert_transition(case.status, target)
                        case.status = target
                        case.current_version += 1
                    proposed_action = (
                        {
                            "action": "RESOLVE_INVOICE_EXCEPTION",
                            "payload": task.proposed_action.get("payload", {}),
                        }
                        if case.case_type == "INVOICE_EXCEPTION"
                        else {
                            "action": "CREATE_VENDOR",
                            "payload": task.evidence_packet.get("vendor", {}),
                        }
                    )
                    if interrupt_kind == "CONTROL_REVIEW":
                        proposed_action["action"] = "RESOLVE_CONTROL_REVIEW"
                    next_task = ApprovalTask(
                        tenant_id=tenant_id,
                        case_id=case_id,
                        run_id=run_id,
                        task_type=next_task_type,
                        assigned_role=assigned_role,
                        proposed_action=proposed_action,
                        evidence_packet=task.evidence_packet,
                        evidence_hash=task.evidence_hash,
                        case_version=case.current_version,
                    )
                    session.add(next_task)
                    run.current_node = (
                        "control_review"
                        if interrupt_kind == "CONTROL_REVIEW"
                        else "approval_interrupt"
                    )
                    await append_case_event(
                        session,
                        tenant_id=tenant_id,
                        case_id=case_id,
                        event_type=(
                            "CONTROL_REVIEW_REQUIRED"
                            if interrupt_kind == "CONTROL_REVIEW"
                            else "FINAL_APPROVAL_REQUIRED"
                        ),
                        actor_type="SYSTEM",
                        actor_id="agent-worker",
                        payload={
                            "run_id": str(run_id),
                            "task_type": next_task_type,
                            "evidence_hash": task.evidence_hash,
                        },
                    )
                else:
                    raise RuntimeError("UNEXPECTED_WORKFLOW_INTERRUPT")
                run.status = "INTERRUPTED"
            else:
                if result.get("outcome") == "REANALYZE":
                    run.status = "QUEUED"
                    run.current_node = "reanalysis_queued"
                    analysis_event = (
                        "invoice.analysis.requested.v1"
                        if case.case_type == "INVOICE_EXCEPTION"
                        else "agent.analysis.requested.v1"
                    )
                    enqueue_event(
                        session,
                        tenant_id=tenant_id,
                        aggregate_type="case",
                        aggregate_id=case_id,
                        aggregate_version=case.current_version,
                        event_type=analysis_event,
                        idempotency_key=(
                            f"reanalysis:{run_id}:v{case.current_version}"
                        ),
                        payload={
                            "case_id": str(case_id),
                            "run_id": str(run_id),
                        },
                    )
                else:
                    run.status = "COMPLETED"
                    run.current_node = "finished"
                    run.completed_at = datetime.now(UTC)
            run.state_version += 1
            run.state_json = {
                **run.state_json,
                "human_response": result.get("human_response"),
                "outcome": result.get("outcome"),
                "current_stage": result.get("current_stage"),
            }
            await append_audit(
                session,
                tenant_id=tenant_id,
                case_id=case_id,
                actor_type="SYSTEM",
                actor_id="agent-worker",
                action="WORKFLOW_HUMAN_RESUMED",
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                metadata={
                    "decision": decision,
                    "task_id": str(task_id),
                    "evidence_hash": payload["evidence_hash"],
                },
            )
            session.add(
                InboxReceipt(
                    consumer_name="agent-worker",
                    event_id=event_id,
                    tenant_id=tenant_id,
                )
            )


async def resume_erp_confirmation(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    payload = envelope["payload"]
    case_id = uuid.UUID(payload["case_id"])
    run_id = uuid.UUID(payload["run_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(
                InboxReceipt,
                {"consumer_name": "agent-worker", "event_id": event_id},
            ):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            operation = await session.get(
                ErpOperation,
                uuid.UUID(payload["operation_id"]),
            )
            if (
                not case
                or case.tenant_id != tenant_id
                or not run
                or not operation
                or operation.case_id != case_id
            ):
                raise RuntimeError("ERP_CONFIRMATION_CONTEXT_NOT_FOUND")
            async with tenant_workflow(str(tenant_id)) as graph:
                result = await graph.ainvoke(
                    Command(
                        resume={
                            "status": payload["status"],
                            "operation_id": payload["operation_id"],
                            "provider_reference": payload.get(
                                "provider_reference"
                            ),
                            "error_code": payload.get("error_code"),
                        }
                    ),
                    workflow_config(run.thread_id),
                )
            if result.get("__interrupt__"):
                raise RuntimeError("ERP_CONFIRMATION_DID_NOT_COMPLETE")
            if payload["status"] == "SUCCEEDED":
                if case.status != CaseStatus.ERP_SYNC_PENDING:
                    raise RuntimeError("ERP_CONFIRMATION_STATE_MISMATCH")
                assert_transition(case.status, CaseStatus.COMPLETED)
                case.status = CaseStatus.COMPLETED
                case.resolved_at = datetime.now(UTC)
                run.status = "COMPLETED"
                event_type = "WORKFLOW_COMPLETED"
            else:
                if case.status == CaseStatus.ERP_SYNC_PENDING:
                    assert_transition(case.status, CaseStatus.ERP_SYNC_FAILED)
                    case.status = CaseStatus.ERP_SYNC_FAILED
                run.status = "INTERRUPTED"
                event_type = "WORKFLOW_ERP_FAILED"
            case.current_version += 1
            run.current_node = result["current_stage"]
            run.completed_at = (
                datetime.now(UTC)
                if run.status == "COMPLETED"
                else None
            )
            run.state_version += 1
            run.state_json = {
                **run.state_json,
                "erp_confirmation": result.get("erp_confirmation"),
                "outcome": result.get("outcome"),
                "current_stage": result.get("current_stage"),
            }
            await append_case_event(
                session,
                tenant_id=tenant_id,
                case_id=case_id,
                event_type=event_type,
                actor_type="SYSTEM",
                actor_id="agent-worker",
                payload={
                    "run_id": str(run_id),
                    "provider_reference": payload.get("provider_reference"),
                },
            )
            await append_audit(
                session,
                tenant_id=tenant_id,
                case_id=case_id,
                actor_type="SYSTEM",
                actor_id="agent-worker",
                action=event_type,
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                metadata={
                    "operation_id": payload["operation_id"],
                    "provider_reference": payload.get("provider_reference"),
                },
            )
            if run.status == "COMPLETED":
                notification = Notification(
                    tenant_id=tenant_id,
                    user_id=case.requester_user_id,
                    case_id=case_id,
                    notification_type="CASE_COMPLETED",
                    title=f"Case {case.case_number} completed",
                    body="The approved operation was explicitly confirmed by the ERP.",
                )
                session.add(notification)
                await session.flush()
                enqueue_event(
                    session,
                    tenant_id=tenant_id,
                    aggregate_type="notification",
                    aggregate_id=notification.notification_id,
                    aggregate_version=1,
                    event_type="notification.delivery.requested.v1",
                    idempotency_key=(
                        f"notification.delivery:"
                        f"{notification.notification_id}:1"
                    ),
                    payload={
                        "notification_id": str(
                            notification.notification_id
                        ),
                        "user_id": str(case.requester_user_id),
                        "attempt": 1,
                    },
                )
            session.add(
                InboxReceipt(
                    consumer_name="agent-worker",
                    event_id=event_id,
                    tenant_id=tenant_id,
                )
            )


async def dispatch(envelope: dict) -> None:
    event_type = envelope["event_type"]
    if event_type == "case.submitted.v1":
        await handle_case_submitted(envelope)
    elif event_type in {
        "approval.approved.v1",
        "approval.rejected.v1",
        "approval.more_info.v1",
        "approval.escalated.v1",
        "review.resolved.v1",
        "clarification.answered.v1",
    }:
        await resume_human_decision(envelope)
    elif event_type == "agent.erp.confirmed.v1":
        await resume_erp_confirmation(envelope)
    else:
        await run_analysis(envelope)


if __name__ == "__main__":
    asyncio.run(
        consume(
            "agent-worker",
            [
                "case.submitted.v1",
                "agent.analysis.requested.v1",
                "approval.approved.v1",
                "approval.rejected.v1",
                "approval.more_info.v1",
                "approval.escalated.v1",
                "review.resolved.v1",
                "clarification.answered.v1",
                "agent.erp.confirmed.v1",
            ],
            dispatch,
        )
    )
