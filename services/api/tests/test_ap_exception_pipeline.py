from app.domain.invoices import check_tolerance
from app.workers.invoice_agent import check_missing_po, check_tax_mismatch

def test_tolerance_logic():
    # Within tolerance (<= 50.0 LKR AND <= 5%)
    assert check_tolerance(variance_amount=25.0, variance_pct=2.5, threshold_amount=50.0, threshold_pct=5.0) is True
    # Exceeds tolerance (> 50.0 LKR)
    assert check_tolerance(variance_amount=150.0, variance_pct=2.5, threshold_amount=50.0, threshold_pct=5.0) is False

def test_missing_po_detection():
    extracted_no_po = {"invoice_number": "INV-100", "po_reference": None}
    all_docs_no_po = []
    po_data_empty = {"lines": {}}
    assert check_missing_po(extracted_no_po, all_docs_no_po, po_data_empty) is True

    po_data_present = {"lines": {1: {"description": "Item 1"}}}
    assert check_missing_po(extracted_no_po, all_docs_no_po, po_data_present) is False

def test_tax_mismatch_detection():
    extracted_15 = {"tax_rate": 15.0}
    po_18 = {"tax_rate": 18.0}
    res = check_tax_mismatch(extracted_15, po_18)
    assert res["mismatch"] is True
    assert "Tax mismatch detected" in res["message"]

    extracted_18 = {"tax_rate": 18.0}
    res_clean = check_tax_mismatch(extracted_18, po_18)
    assert res_clean["mismatch"] is False
