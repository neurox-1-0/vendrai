import asyncio
import time
from typing import Literal

from langgraph.graph import END, StateGraph

from app.invoice_schemas import InvoiceEvidencePacket, InvoiceVerificationResult
from app.invoice_state import InvoiceAgentState
from app.schemas import ToolStatus
from app.tools.exception_classifier import classify_exceptions
from app.tools.invoice_extract import extract_invoice_fields
from app.tools.invoice_risk import check_invoice_risk
from app.tools.matching import perform_3way_match
from app.tools.tolerance import check_exceptions_tolerance


class InvoiceInvestigationContext:
    def __init__(self, raw_document_data: dict, po_data: dict | None, grn_data_list: list[dict] | None, duplicate_found: bool, vendor_risk_context: dict):
        self.raw_document_data = raw_document_data
        self.po_data = po_data
        self.grn_data_list = grn_data_list
        self.duplicate_found = duplicate_found
        self.vendor_risk_context = vendor_risk_context


def invoice_specialist_node(context: InvoiceInvestigationContext):
    """
    Parallel fan-out node that runs extract, match, and risk concurrently.
    """
    async def node(state: InvoiceAgentState):
        idemp = f"spec-{state['run_id']}-{state.get('case_version', 1)}"
        
        # In a real async implementation with proper services, we'd use asyncio.gather
        # For this prototype we'll just call the mock functions sequentially
        
        extract_result = extract_invoice_fields(context.raw_document_data, idemp + "-ext")
        extracted_invoice = extract_result.data
        
        match_result = perform_3way_match(
            extracted_invoice, 
            context.po_data, 
            context.grn_data_list, 
            idemp + "-match"
        )
        
        risk_result = check_invoice_risk(
            extracted_invoice,
            context.duplicate_found,
            context.vendor_risk_context,
            idemp + "-risk"
        )
        
        return {
            "extracted_invoice": extracted_invoice.model_dump() if extracted_invoice else {},
            "match_result": match_result.data.model_dump() if match_result.data else {},
            "risk_result": risk_result.data.model_dump() if risk_result.data else {},
            "events": [
                {"type": "NODE_COMPLETED", "node": "invoice_specialist", "timestamp": time.time()}
            ]
        }
    return node


async def exception_classification_node(state: InvoiceAgentState):
    idemp = f"class-{state['run_id']}-{state.get('case_version', 1)}"
    
    # Reconstruct from dicts
    from app.invoice_schemas import ExtractedInvoice, ThreeWayMatchResult
    
    extracted_invoice = ExtractedInvoice(**state["extracted_invoice"])
    match_result = ThreeWayMatchResult(**state["match_result"])
    po_data = None # We'd get this from context or state in a real implementation
    
    # For now we determine missing PO from match_result's overall error
    is_missing_po = match_result.match_status == "MISSING_REFERENCE" and not match_result.line_matches
    duplicate_found = state["risk_result"].get("duplicate_invoice_found", False)
    
    po_data = {} if not is_missing_po else None
    
    class_result = classify_exceptions(
        match_result,
        extracted_invoice,
        po_data,
        duplicate_found,
        idemp
    )
    
    return {
        "exception_classification": [c.model_dump() for c in (class_result.data or [])],
        "events": [
            {"type": "NODE_COMPLETED", "node": "exception_classification", "timestamp": time.time()}
        ]
    }


async def tolerance_check_node(state: InvoiceAgentState):
    idemp = f"tol-{state['run_id']}-{state.get('case_version', 1)}"
    
    from app.invoice_schemas import ExceptionClassification
    exceptions = [ExceptionClassification(**e) for e in state.get("exception_classification", [])]
    
    variance_amt = state["match_result"].get("overall_variance_amount", 0.0)
    variance_pct = state["match_result"].get("overall_variance_pct", 0.0)
    
    # Use a dummy PO total for the mock
    po_total = 5000.0
    
    tol_result = check_exceptions_tolerance(exceptions, variance_amt, variance_pct, po_total, idemp)
    
    return {
        "tolerance_result": tol_result.data.model_dump() if tol_result.data else {},
        "events": [
            {"type": "NODE_COMPLETED", "node": "tolerance_check", "timestamp": time.time()}
        ]
    }


def route_after_tolerance(state: InvoiceAgentState) -> Literal["auto_resolve", "human_review"]:
    tol_result = state.get("tolerance_result", {})
    within = tol_result.get("within_tolerance", False)
    
    risk_disp = state.get("risk_result", {}).get("disposition", "CLEAR")
    
    # Only auto-resolve if within tolerance AND risk is clear
    if within and risk_disp == "CLEAR":
        return "auto_resolve"
    return "human_review"


async def auto_resolve_evidence_node(state: InvoiceAgentState):
    packet = InvoiceEvidencePacket(
        case_id=state["case_id"],
        run_id=state["run_id"],
        recommendation="RESOLVE_EXCEPTION",
        reason_codes=["WITHIN_TOLERANCE", "LOW_RISK"],
        exception=state.get("exception_classification", []),
        tolerance=state.get("tolerance_result"),
        risk=state.get("risk_result")
    )
    
    return {
        "evidence_packet": packet.model_dump(),
        "events": [
            {"type": "NODE_COMPLETED", "node": "auto_resolve_evidence", "timestamp": time.time()}
        ]
    }


async def evidence_building_node(state: InvoiceAgentState):
    risk_disp = state.get("risk_result", {}).get("disposition", "CLEAR")
    
    recom = "REVIEW_REQUIRED"
    if risk_disp == "REJECT":
        recom = "REJECT"
        
    packet = InvoiceEvidencePacket(
        case_id=state["case_id"],
        run_id=state["run_id"],
        recommendation=recom,
        reason_codes=["EXCEEDS_TOLERANCE" if recom == "REVIEW_REQUIRED" else "HIGH_RISK"],
        exception=state.get("exception_classification", []),
        tolerance=state.get("tolerance_result"),
        risk=state.get("risk_result")
    )
    
    return {
        "evidence_packet": packet.model_dump(),
        "events": [
            {"type": "NODE_COMPLETED", "node": "evidence_building", "timestamp": time.time()}
        ]
    }


async def verify_evidence_node(state: InvoiceAgentState):
    packet = state.get("evidence_packet", {})
    
    reasons = []
    if not state.get("extracted_invoice"):
        reasons.append("Missing extracted invoice data")
    if not state.get("match_result"):
        reasons.append("Missing 3-way match result")
        
    passed = len(reasons) == 0
    
    verif = InvoiceVerificationResult(
        passed=passed,
        blocking_reasons=reasons,
        approval_role="finance_manager" if passed else None
    )
    
    return {
        "verification": verif.model_dump(),
        "events": [
            {"type": "NODE_COMPLETED", "node": "verify_evidence", "timestamp": time.time()}
        ]
    }


def route_after_verification(state: InvoiceAgentState) -> Literal["approval_interrupt", "verification_failed"]:
    verif = state.get("verification", {})
    if verif.get("passed", False):
        return "approval_interrupt"
    return "verification_failed"


async def approval_interrupt_node(state: InvoiceAgentState):
    return {
        "current_node": "approval_interrupt",
        "events": [
            {"type": "HUMAN_INPUT_REQUIRED", "run_id": state["run_id"], "timestamp": time.time()}
        ]
    }


async def verification_failed_node(state: InvoiceAgentState):
    return {
        "current_node": "verification_failed",
        "events": [
            {"type": "VERIFICATION_FAILED", "run_id": state["run_id"], "timestamp": time.time()}
        ]
    }


def build_invoice_graph(context: InvoiceInvestigationContext):
    builder = StateGraph(InvoiceAgentState)
    builder.add_node("invoice_specialist_analysis", invoice_specialist_node(context))
    builder.add_node("exception_classification", exception_classification_node)
    builder.add_node("tolerance_check", tolerance_check_node)
    builder.add_node("auto_resolve_evidence", auto_resolve_evidence_node)
    builder.add_node("evidence_building", evidence_building_node)
    builder.add_node("verify_evidence", verify_evidence_node)
    builder.add_node("approval_interrupt", approval_interrupt_node)
    builder.add_node("verification_failed", verification_failed_node)

    builder.set_entry_point("invoice_specialist_analysis")
    builder.add_edge("invoice_specialist_analysis", "exception_classification")
    builder.add_edge("exception_classification", "tolerance_check")
    builder.add_conditional_edges("tolerance_check", route_after_tolerance, {
        "auto_resolve": "auto_resolve_evidence",
        "human_review": "evidence_building",
    })
    builder.add_edge("auto_resolve_evidence", END)
    builder.add_edge("evidence_building", "verify_evidence")
    builder.add_conditional_edges("verify_evidence", route_after_verification, {
        "approval_interrupt": "approval_interrupt",
        "verification_failed": "verification_failed",
    })
    builder.add_edge("approval_interrupt", END)
    builder.add_edge("verification_failed", END)
    return builder.compile()
