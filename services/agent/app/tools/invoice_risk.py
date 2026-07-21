import time

from app.invoice_schemas import ExtractedInvoice, FraudSignal, InvoiceRiskAssessment
from app.schemas import ToolResult, ToolStatus


def check_invoice_risk(
    invoice: ExtractedInvoice,
    duplicate_found: bool,
    vendor_risk_context: dict,
    idempotency_key: str,
) -> ToolResult[InvoiceRiskAssessment]:
    """
    Deterministic invoice fraud/risk signal checks.
    """
    started = time.perf_counter()
    signals = []
    
    # Check for round amounts (potential fraud)
    if invoice.total_amount > 0 and invoice.total_amount % 1000 == 0:
        signals.append(FraudSignal(
            signal_type="ROUND_AMOUNT",
            description=f"Invoice total amount {invoice.total_amount} is a perfect round number.",
            severity="MEDIUM"
        ))
        
    # Check for just-below-threshold (e.g. $9,999)
    if 9900 <= invoice.total_amount < 10000:
        signals.append(FraudSignal(
            signal_type="BELOW_THRESHOLD",
            description=f"Invoice total amount {invoice.total_amount} is just below the 10k threshold.",
            severity="HIGH"
        ))
        
    if duplicate_found:
        signals.append(FraudSignal(
            signal_type="DUPLICATE_INVOICE",
            description="A duplicate invoice matching number, vendor, and amount was found.",
            severity="CRITICAL"
        ))
        
    if vendor_risk_context.get("recent_bank_change"):
        signals.append(FraudSignal(
            signal_type="VENDOR_BANK_CHANGE",
            description="The vendor changed their bank account details in the last 7 days.",
            severity="HIGH"
        ))
        
    disposition = "CLEAR"
    if any(s.severity == "CRITICAL" for s in signals):
        disposition = "REJECT"
    elif signals:
        disposition = "REVIEW"

    assessment = InvoiceRiskAssessment(
        disposition=disposition,
        fraud_signals=signals,
        duplicate_invoice_found=duplicate_found
    )
    
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=assessment,
        provider_version="invoice-risk-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000)
    )
