import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from app.agents.workflow import tenant_workflow, workflow_config
from app.config import settings
from app.domain.cases import CaseStatus, assert_transition
from app.domain.intelligence import (
    current_sanctions_datasets,
    sanctions_name_score,
    score_duplicate,
)
from app.domain.security import canonical_hash, normalize_vendor_name
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
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from langgraph.types import Command
from sqlalchemy import select


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
    )
    return result.score, result.signals


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

            vendors = (await session.execute(select(Vendor).where(Vendor.tenant_id == tenant_id))).scalars().all()
            duplicate_items: list[dict] = []
            for vendor in vendors:
                score, signals = duplicate_score(fields, vendor)
                if score >= 0.45:
                    review = score >= 0.70 or bool(signals["tax_exact"] or signals["bank_exact"])
                    session.add(DuplicateCandidateRecord(
                        tenant_id=tenant_id, case_id=case_id, vendor_id=vendor.vendor_id,
                        score=score, signals=signals, review_required=review,
                    ))
                    duplicate_items.append({"vendor_id": str(vendor.vendor_id), "name": vendor.legal_name, "score": score, "signals": signals, "review_required": review})

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
            risk_candidates: list[dict] = []
            query_name = fields["legal_name_normalized"]
            for entity in sanctions_entities:
                names = [entity.primary_name, *entity.aliases]
                best_name, best_score = max(
                    ((name, sanctions_name_score(query_name, name)) for name in names),
                    key=lambda item: item[1],
                )
                if best_score >= 0.84:
                    dataset = next(item for item in datasets if item.dataset_id == entity.dataset_id)
                    risk_candidates.append({"source": dataset.source, "version": dataset.version, "entity_id": entity.external_id, "matched_name": best_name, "score": round(best_score, 4)})
            sanctions_unavailable = bool(missing_sanctions or stale_sanctions)
            risk_disposition = (
                "UNAVAILABLE"
                if sanctions_unavailable
                else "POSSIBLE_MATCH"
                if risk_candidates
                else "CLEAR"
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

            policy_query = "new vendor onboarding required documents bank details sanctions screening human approval"
            policy_items, policy_error = await retrieve_policy(tenant_id, policy_query)

            unresolved = []
            if not legal_name:
                unresolved.append("legal_name")
            critical_unverified = [field.field_name for field in fields_rows if field.field_name in {"tax_id", "bank_account"} and not field.human_verified and (field.confidence or 0) < 0.90]
            unresolved.extend(critical_unverified)
            blockers = []
            if risk_disposition == "UNAVAILABLE":
                blockers.append("SANCTIONS_DATA_UNAVAILABLE")
            if not policy_items:
                blockers.append(policy_error or "INSUFFICIENT_POLICY_EVIDENCE")
            reason_codes = list(blockers)
            if any(item["review_required"] for item in duplicate_items):
                reason_codes.append("POSSIBLE_DUPLICATE")
            if risk_disposition == "POSSIBLE_MATCH":
                reason_codes.append("SANCTIONS_REVIEW_REQUIRED")
            recommendation = "REQUEST_INFORMATION" if unresolved else "REVIEW_REQUIRED" if reason_codes else "CREATE_VENDOR"
            packet = {
                "case_id": str(case_id), "run_id": str(run_id), "recommendation": recommendation,
                "reason_codes": reason_codes, "vendor": {"legal_name": legal_name, "registered_country": fields.get("registered_country")},
                "duplicate_candidates": duplicate_items, "risk": {"disposition": risk_disposition, "candidates": risk_candidates},
                "policy_clauses": policy_items, "unresolved_items": sorted(set(unresolved)),
            }
            evidence_hash = canonical_hash(packet)
            evidence_rows: list[EvidenceItem] = []
            for item in policy_items:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="POLICY",
                    source_id=f"{item['policy_code']}:{item['version']}:{item['clause_id']}",
                    source_locator={"effective_date": item["effective_date"]}, claim=item["content"],
                    reason_code="POLICY_CLAUSE", confidence=item.get("rerank_score"),
                )
                evidence_rows.append(evidence)
                session.add(evidence)
            for item in duplicate_items:
                evidence = EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="VENDOR_MASTER",
                    source_id=item["vendor_id"], source_locator={"signals": item["signals"]},
                    claim=f"Potential duplicate: {item['name']}", reason_code="DUPLICATE_SCORE", confidence=item["score"],
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
                "required_reviews": [
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
                    )
                    if required
                ],
                "completed_reviews": [],
                "deterministic_packet": graph_packet,
                "current_stage": "deterministic_checks_complete",
            }
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
                    questions=[{"field": item, "question": f"Please confirm or provide {item.replace('_', ' ')}."} for item in sorted(set(unresolved))],
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
                elif task_type == "SANCTIONS_REVIEW":
                    case.status = CaseStatus.RISK_REVIEW
                    assigned_role = "compliance_approver"
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
