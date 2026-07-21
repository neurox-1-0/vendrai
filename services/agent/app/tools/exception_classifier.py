import time

from app.domain.invoices import ExceptionSeverity, ExceptionType, MatchStatus
from app.invoice_schemas import ExceptionClassification, ExtractedInvoice, ThreeWayMatchResult
from app.schemas import ToolResult, ToolStatus


def classify_exceptions(
    match_result: ThreeWayMatchResult,
    invoice: ExtractedInvoice,
    po_data: dict | None,
    duplicate_found: bool,
    idempotency_key: str,
) -> ToolResult[list[ExceptionClassification]]:
    """
    Deterministic exception classification based on match results.
    """
    started = time.perf_counter()
    exceptions = []

    if duplicate_found:
        exceptions.append(ExceptionClassification(
            exception_type=ExceptionType.DUPLICATE_INVOICE,
            severity=ExceptionSeverity.CRITICAL,
            confidence=1.0,
            mismatch_details={"message": "A duplicate invoice was found in the system."},
            affected_lines=[]
        ))

    if not po_data:
        exceptions.append(ExceptionClassification(
            exception_type=ExceptionType.MISSING_PO,
            severity=ExceptionSeverity.HIGH,
            confidence=1.0,
            mismatch_details={"message": "No valid purchase order found for this invoice."},
            affected_lines=[]
        ))

    # Evaluate line matches
    price_var_lines = []
    qty_var_lines = []
    
    for match in match_result.line_matches:
        if not match.invoice_line:
            continue
            
        line_num = match.invoice_line.line_number
        if match.price_variance != 0:
            price_var_lines.append(line_num)
        if match.quantity_variance != 0:
            qty_var_lines.append(line_num)
            
    if price_var_lines:
        exceptions.append(ExceptionClassification(
            exception_type=ExceptionType.PRICE_VARIANCE,
            severity=ExceptionSeverity.MEDIUM,
            confidence=1.0,
            mismatch_details={"message": f"Price variance found on lines: {price_var_lines}"},
            affected_lines=price_var_lines
        ))
        
    if qty_var_lines:
        exceptions.append(ExceptionClassification(
            exception_type=ExceptionType.QUANTITY_MISMATCH,
            severity=ExceptionSeverity.MEDIUM,
            confidence=1.0,
            mismatch_details={"message": f"Quantity mismatch found on lines: {qty_var_lines}"},
            affected_lines=qty_var_lines
        ))

    # Tax check
    expected_tax = sum(line.amount * line.tax_rate for line in invoice.line_items)
    if abs(invoice.tax_amount - expected_tax) > 0.1: # 10 cents tolerance for rounding
        exceptions.append(ExceptionClassification(
            exception_type=ExceptionType.TAX_ISSUE,
            severity=ExceptionSeverity.MEDIUM,
            confidence=1.0,
            mismatch_details={"message": f"Tax calculated ({expected_tax}) does not match invoice tax ({invoice.tax_amount})."},
            affected_lines=[]
        ))

    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=exceptions,
        provider_version="classifier-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000)
    )
