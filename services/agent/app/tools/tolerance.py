import time

from app.domain.invoices import check_tolerance
from app.invoice_schemas import ExceptionClassification, ToleranceResult
from app.schemas import ToolResult, ToolStatus


def check_exceptions_tolerance(
    exceptions: list[ExceptionClassification],
    overall_variance_amount: float,
    overall_variance_pct: float,
    po_total: float,
    idempotency_key: str,
) -> ToolResult[ToleranceResult]:
    """
    Checks if the overall variances are within the acceptable tolerance levels.
    """
    started = time.perf_counter()
    
    # Mocking policy thresholds. In reality, these would come from the Policy Agent.
    # E.g., < $1000 PO has 5% tolerance, otherwise 2%. Max $50.
    threshold_pct = 5.0 if po_total < 1000 else 2.0
    threshold_amount = 50.0
    
    # Check if ANY exception type strictly denies auto-resolution
    for exc in exceptions:
        if exc.exception_type in ("DUPLICATE_INVOICE", "MISSING_PO"):
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data=ToleranceResult(
                    within_tolerance=False,
                    threshold_amount=0.0,
                    threshold_pct=0.0,
                    actual_variance=overall_variance_amount,
                    policy_ref="POLICY-INV-001 (Strict denial for duplicates/missing POs)",
                    exception_type=exc.exception_type
                ),
                provider_version="tolerance-engine-v1",
                idempotency_key=idempotency_key,
                latency_ms=round((time.perf_counter() - started) * 1000)
            )

    within = check_tolerance(
        variance_amount=overall_variance_amount,
        variance_pct=overall_variance_pct,
        threshold_amount=threshold_amount,
        threshold_pct=threshold_pct
    )
    
    primary_exception = exceptions[0].exception_type if exceptions else "NONE"
    
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=ToleranceResult(
            within_tolerance=within,
            threshold_amount=threshold_amount,
            threshold_pct=threshold_pct,
            actual_variance=overall_variance_amount,
            policy_ref="POLICY-INV-TOL-001",
            exception_type=primary_exception
        ),
        provider_version="tolerance-engine-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000)
    )
