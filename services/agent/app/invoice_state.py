import operator
from typing import Annotated, Any, TypedDict


class InvoiceAgentState(TypedDict, total=False):
    case_id: str
    run_id: str
    tenant_id: str
    case_version: int
    current_node: str
    
    # Invoice-specific state components
    extracted_invoice: dict[str, Any]
    match_result: dict[str, Any]           # 3-way match output
    risk_result: dict[str, Any]            # fraud/risk signals
    policy_result: dict[str, Any]          # tolerance rules & approval matrix
    exception_classification: dict[str, Any]
    tolerance_result: dict[str, Any]
    evidence_packet: dict[str, Any]
    verification: dict[str, Any]
    approval_decision: dict[str, Any]
    
    # Reducer pattern for collecting events emitted by nodes
    events: Annotated[list[dict[str, Any]], operator.add]
