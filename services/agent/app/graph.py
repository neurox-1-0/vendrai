import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.schemas import (
    EvidencePacket,
    EvidenceRef,
    ExtractedVendor,
    PolicyClause,
    RiskAssessment,
    SanctionsEntity,
    VendorRecord,
    VerificationResult,
)
from app.state import AgentState
from app.tools.duplicate import find_duplicates
from app.tools.policy import retrieve_policies
from app.tools.risk import screen_sanctions


@dataclass(frozen=True)
class InvestigationContext:
    vendors: list[VendorRecord]
    sanctions_entities: list[SanctionsEntity]
    policies: list[PolicyClause]


def _event(event_type: str, **payload: Any) -> dict[str, Any]:
    return {"type": event_type, "payload": payload}


def specialist_node(context: InvestigationContext):
    async def run(state: AgentState) -> dict[str, Any]:
        vendor = ExtractedVendor.model_validate(state["extracted_vendor"])
        case_id = state["case_id"]
        duplicate_task = asyncio.to_thread(find_duplicates, vendor, context.vendors, f"{case_id}:duplicate")
        sanctions_task = asyncio.to_thread(screen_sanctions, vendor, context.sanctions_entities, f"{case_id}:sanctions")
        policy_query = f"new vendor onboarding {vendor.registered_country or ''} approval required documents bank details sanctions"
        policy_task = asyncio.to_thread(retrieve_policies, policy_query, context.policies, f"{case_id}:policy")
        duplicate_result, risk_result, policy_result = await asyncio.gather(duplicate_task, sanctions_task, policy_task)
        return {
            "current_node": "specialist_analysis",
            "duplicate_result": duplicate_result.model_dump(mode="json"),
            "risk_result": risk_result.model_dump(mode="json"),
            "policy_result": policy_result.model_dump(mode="json"),
            "events": [_event(
                "SPECIALIST_ANALYSIS_COMPLETED",
                duplicate_status=duplicate_result.status,
                risk_status=risk_result.status,
                policy_status=policy_result.status,
            )],
        }
    return run


def evidence_node(state: AgentState) -> dict[str, Any]:
    vendor = ExtractedVendor.model_validate(state["extracted_vendor"])
    duplicate_result = state["duplicate_result"]
    risk_result = state["risk_result"]
    policy_result = state["policy_result"]
    duplicates = duplicate_result.get("data") or []
    risk = RiskAssessment.model_validate(risk_result.get("data") or {"disposition": "UNAVAILABLE"})
    policy_data = policy_result.get("data") or {"disposition": "INSUFFICIENT_EVIDENCE", "clauses": []}
    policies = [PolicyClause.model_validate(item) for item in policy_data.get("clauses", [])]
    evidence: list[EvidenceRef] = []
    for result in (duplicate_result, risk_result, policy_result):
        evidence.extend(EvidenceRef.model_validate(item) for item in result.get("evidence", []))
    evidence.extend(EvidenceRef(
        source_type="POLICY", source_id=f"{clause.policy_id}:{clause.version}:{clause.clause_id}",
        locator={"effective_date": clause.effective_date}, reason_code="POLICY_CLAUSE", confidence=clause.score,
    ) for clause in policies)
    unresolved = list(vendor.fields_requiring_confirmation)
    reason_codes: list[str] = []
    if any(item.get("review_required") for item in duplicates):
        reason_codes.append("POSSIBLE_DUPLICATE")
    if risk.disposition == "POSSIBLE_MATCH":
        reason_codes.append("SANCTIONS_REVIEW_REQUIRED")
    elif risk.disposition == "UNAVAILABLE":
        reason_codes.append("SANCTIONS_DATA_UNAVAILABLE")
        unresolved.append("sanctions_screening")
    if policy_data.get("disposition") != "SUPPORTED":
        reason_codes.append("INSUFFICIENT_POLICY_EVIDENCE")
        unresolved.append("applicable_policy")
    if not vendor.legal_name:
        unresolved.append("legal_name")
    recommendation: Literal["CREATE_VENDOR", "REJECT", "REQUEST_INFORMATION", "REVIEW_REQUIRED"]
    if unresolved:
        recommendation = "REQUEST_INFORMATION"
    elif reason_codes:
        recommendation = "REVIEW_REQUIRED"
    else:
        recommendation = "CREATE_VENDOR"
    packet = EvidencePacket(
        case_id=state["case_id"], run_id=state["run_id"], recommendation=recommendation,
        reason_codes=reason_codes, extracted_vendor=vendor,
        duplicate_candidates=duplicates, risk=risk, policy_clauses=policies,
        evidence=evidence, unresolved_items=sorted(set(unresolved)),
    )
    return {
        "current_node": "evidence_building",
        "evidence_packet": packet.model_dump(mode="json"),
        "events": [_event("EVIDENCE_PACKET_BUILT", recommendation=recommendation, unresolved_count=len(unresolved))],
    }


def verifier_node(state: AgentState) -> dict[str, Any]:
    packet = EvidencePacket.model_validate(state["evidence_packet"])
    blockers: list[str] = []
    if not packet.extracted_vendor.legal_name:
        blockers.append("LEGAL_NAME_MISSING")
    if packet.risk.disposition == "UNAVAILABLE":
        blockers.append("SANCTIONS_SCREENING_INCOMPLETE")
    if not packet.policy_clauses:
        blockers.append("POLICY_EVIDENCE_MISSING")
    if packet.recommendation == "CREATE_VENDOR" and not packet.evidence:
        blockers.append("EVIDENCE_MISSING")
    verification = VerificationResult(passed=not blockers, blocking_reasons=blockers)
    return {
        "current_node": "approval_interrupt" if verification.passed else "verification_failed",
        "verification": verification.model_dump(mode="json"),
        "events": [_event("VERIFICATION_COMPLETED", passed=verification.passed, blocking_reasons=blockers)],
    }


def route_after_verification(state: AgentState) -> str:
    return "approval_interrupt" if state["verification"]["passed"] else "verification_failed"


def approval_interrupt_node(state: AgentState) -> dict[str, Any]:
    # Durable pause is persisted by the worker/API as an ApprovalTask. No tool is executed here.
    return {"current_node": "approval_interrupt", "events": [_event("HUMAN_APPROVAL_REQUIRED")]}


def verification_failed_node(state: AgentState) -> dict[str, Any]:
    return {"current_node": "verification_failed", "events": [_event("RUN_BLOCKED", reasons=state["verification"]["blocking_reasons"])]}


def build_graph(context: InvestigationContext):
    builder = StateGraph(AgentState)
    builder.add_node("specialist_analysis", specialist_node(context))
    builder.add_node("evidence_building", evidence_node)
    builder.add_node("verify_evidence", verifier_node)
    builder.add_node("approval_interrupt", approval_interrupt_node)
    builder.add_node("verification_failed", verification_failed_node)
    builder.set_entry_point("specialist_analysis")
    builder.add_edge("specialist_analysis", "evidence_building")
    builder.add_edge("evidence_building", "verify_evidence")
    builder.add_conditional_edges("verify_evidence", route_after_verification, {
        "approval_interrupt": "approval_interrupt",
        "verification_failed": "verification_failed",
    })
    builder.add_edge("approval_interrupt", END)
    builder.add_edge("verification_failed", END)
    return builder.compile()


async def run_investigation(initial_state: AgentState, context: InvestigationContext) -> AgentState:
    graph = build_graph(context)
    return await graph.ainvoke(initial_state)
