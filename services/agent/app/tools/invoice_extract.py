import time

from app.invoice_schemas import ExtractedInvoice
from app.schemas import ToolResult, ToolStatus


def extract_invoice_fields(
    raw_document_data: dict,
    idempotency_key: str,
) -> ToolResult[ExtractedInvoice]:
    """
    Mock implementation of invoice field extraction.
    In a real system, this would call Docling/OCR and map to ExtractedInvoice.
    """
    started = time.perf_counter()
    
    # Mocked deterministic logic for the sake of the MVP
    # This relies on the mock ERP and test fixtures being predictable
    
    vendor_id_ref = raw_document_data.get("vendor_id_ref", "VND-100")
    po_number = raw_document_data.get("po_number", "PO-2023-001")
    invoice_number = raw_document_data.get("invoice_number", "INV-102030")
    
    total_amount = float(raw_document_data.get("total_amount", 5000.00))
    tax_amount = float(raw_document_data.get("tax_amount", 500.00))
    currency = raw_document_data.get("currency", "USD")
    
    line_items = raw_document_data.get("line_items", [])
    
    extracted = ExtractedInvoice(
        invoice_number=invoice_number,
        vendor_name="Test Vendor Inc.",
        vendor_id_ref=vendor_id_ref,
        po_number=po_number,
        total_amount=total_amount,
        currency=currency,
        tax_amount=tax_amount,
        line_items=line_items,
        invoice_date="2023-10-01",
        due_date="2023-10-31",
        fields_requiring_confirmation=[]
    )
    
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=extracted,
        provider_version="docling-invoice-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )
