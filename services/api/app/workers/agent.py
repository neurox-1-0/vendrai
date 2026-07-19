import asyncio
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

import httpx

from sqlalchemy import select

from app.domain.cases import CaseStatus
from app.config import settings
from app.domain.security import canonical_hash, normalize_vendor_name
from app.models import (
    AgentRun, ApprovalTask, Case, ClarificationTask, Document, DuplicateCandidateRecord,
    EvidenceItem, ExtractedField, InboxReceipt, Notification, RiskCheck, SanctionsDataset,
    SanctionsEntityRecord, Vendor,
)
from app.services.events import append_audit, append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant


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
    name_score = SequenceMatcher(None, fields.get("legal_name_normalized", ""), vendor.normalized_legal_name).ratio()
    tax_exact = bool(fields.get("tax_id") and vendor.tax_id_hash and fields["tax_id"] == vendor.tax_id_hash.hex())
    bank_exact = bool(fields.get("bank_account") and vendor.bank_account_hash and fields["bank_account"] == vendor.bank_account_hash.hex())
    country_exact = bool(fields.get("registered_country") and vendor.registered_country == fields["registered_country"])
    score = min(1.0, (0.4 if tax_exact else 0) + (0.2 if bank_exact else 0) + 0.35 * name_score + (0.05 if country_exact else 0))
    return round(score, 4), {"tax_exact": tax_exact, "bank_exact": bank_exact, "name_similarity": round(name_score, 4), "country_exact": country_exact}


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

            datasets = (await session.execute(select(SanctionsDataset).where(SanctionsDataset.status == "PUBLISHED"))).scalars().all()
            dataset_ids = [dataset.dataset_id for dataset in datasets]
            sanctions_entities = (await session.execute(
                select(SanctionsEntityRecord).where(SanctionsEntityRecord.dataset_id.in_(dataset_ids))
            )).scalars().all() if dataset_ids else []
            risk_candidates: list[dict] = []
            query_name = fields["legal_name_normalized"]
            for entity in sanctions_entities:
                names = [entity.primary_name, *entity.aliases]
                best_name, best_score = max(
                    ((name, SequenceMatcher(None, query_name, normalize_vendor_name(name)).ratio()) for name in names),
                    key=lambda item: item[1],
                )
                if best_score >= 0.84:
                    dataset = next(item for item in datasets if item.dataset_id == entity.dataset_id)
                    risk_candidates.append({"source": dataset.source, "version": dataset.version, "entity_id": entity.external_id, "matched_name": best_name, "score": round(best_score, 4)})
            risk_disposition = "UNAVAILABLE" if not datasets else "POSSIBLE_MATCH" if risk_candidates else "CLEAR"
            session.add(RiskCheck(
                tenant_id=tenant_id, case_id=case_id, provider="LOCAL_OFFICIAL_LISTS",
                dataset_versions={item.source: item.version for item in datasets},
                status="BLOCKED" if risk_disposition == "UNAVAILABLE" else "SUCCESS",
                disposition=risk_disposition, result={"candidates": risk_candidates},
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
            for item in policy_items:
                session.add(EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="POLICY",
                    source_id=f"{item['policy_code']}:{item['version']}:{item['clause_id']}",
                    source_locator={"effective_date": item["effective_date"]}, claim=item["content"],
                    reason_code="POLICY_CLAUSE", confidence=item.get("rerank_score"),
                ))
            for item in duplicate_items:
                session.add(EvidenceItem(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id, source_type="VENDOR_MASTER",
                    source_id=item["vendor_id"], source_locator={"signals": item["signals"]},
                    claim=f"Potential duplicate: {item['name']}", reason_code="DUPLICATE_SCORE", confidence=item["score"],
                ))

            case.current_version += 1
            if unresolved:
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
                case.status = CaseStatus.APPROVAL_PENDING
                task = ApprovalTask(
                    tenant_id=tenant_id, case_id=case_id, run_id=run_id,
                    task_type="RISK_REVIEW" if risk_disposition == "POSSIBLE_MATCH" else "VENDOR_CREATION",
                    assigned_role="compliance_approver" if risk_disposition == "POSSIBLE_MATCH" else "approver",
                    proposed_action={"action": "CREATE_VENDOR", "payload": packet["vendor"]},
                    evidence_packet=packet, evidence_hash=evidence_hash, case_version=case.current_version,
                )
                session.add(task)
                run.status = "INTERRUPTED"
                run.current_node = "approval_interrupt"
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
            run.state_json = {"evidence_hash": evidence_hash, "recommendation": recommendation, "reason_codes": reason_codes, "unresolved_items": unresolved}
            run.state_version += 1
            await append_case_event(session, tenant_id=tenant_id, case_id=case_id, event_type="ANALYSIS_COMPLETED", actor_type="SYSTEM", actor_id="agent-worker", payload={"run_id": str(run_id), "status": case.status, "recommendation": recommendation, "reason_codes": reason_codes})
            await append_audit(session, tenant_id=tenant_id, case_id=case_id, actor_type="SYSTEM", actor_id="agent-worker", action="ANALYSIS_COMPLETED", resource_type="AGENT_RUN", resource_id=str(run_id), metadata={"evidence_hash": evidence_hash, "reason_codes": reason_codes})
            session.add(InboxReceipt(consumer_name="agent-worker", event_id=event_id, tenant_id=tenant_id))


async def dispatch(envelope: dict) -> None:
    if envelope["event_type"] == "case.submitted.v1":
        await handle_case_submitted(envelope)
    else:
        await run_analysis(envelope)


if __name__ == "__main__":
    asyncio.run(consume("agent-worker", ["case.submitted.v1", "agent.analysis.requested.v1"], dispatch))
