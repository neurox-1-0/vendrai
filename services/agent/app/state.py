from typing import Annotated, Any, TypedDict
import operator


class AgentState(TypedDict, total=False):
    case_id: str
    run_id: str
    tenant_id: str
    case_version: int
    current_node: str
    extracted_vendor: dict[str, Any]
    duplicate_result: dict[str, Any]
    risk_result: dict[str, Any]
    policy_result: dict[str, Any]
    evidence_packet: dict[str, Any]
    verification: dict[str, Any]
    approval_decision: dict[str, Any]
    events: Annotated[list[dict[str, Any]], operator.add]
