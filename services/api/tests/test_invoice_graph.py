import pytest
from app.domain.invoices import MatchStatus, ExceptionType, ExceptionSeverity
from app.invoice_schemas import ExtractedInvoice, InvoiceLineExtracted, ThreeWayMatchResult
from app.tools.exception_classifier import classify_exceptions
from app.tools.tolerance import check_exceptions_tolerance

def test_exception_classifier_duplicate():
    invoice = ExtractedInvoice(
        invoice_number="INV-001",
        total_amount=100.0,
        currency="USD"
    )
    match_result = ThreeWayMatchResult(
        match_status=MatchStatus.FULL_MATCH,
        line_matches=[],
        overall_variance_amount=0.0,
        overall_variance_pct=0.0,
        unmatched_invoice_lines=[],
        unmatched_po_lines=[]
    )
    
    result = classify_exceptions(
        match_result=match_result,
        invoice=invoice,
        po_data={},
        duplicate_found=True,
        idempotency_key="test-1"
    )
    
    assert result.status == "SUCCESS"
    assert any(e.exception_type == ExceptionType.DUPLICATE_INVOICE for e in result.data)

def test_tolerance_strict_denial():
    from app.invoice_schemas import ExceptionClassification
    exceptions = [
        ExceptionClassification(
            exception_type=ExceptionType.MISSING_PO,
            severity=ExceptionSeverity.HIGH,
            confidence=1.0,
            mismatch_details={}
        )
    ]
    
    result = check_exceptions_tolerance(
        exceptions=exceptions,
        overall_variance_amount=0.0,
        overall_variance_pct=0.0,
        po_total=1000.0,
        idempotency_key="test-2"
    )
    
    assert result.status == "SUCCESS"
    assert result.data.within_tolerance is False
    assert result.data.exception_type == ExceptionType.MISSING_PO
