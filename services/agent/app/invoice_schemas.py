from pydantic import BaseModel, Field
from typing import Any


class InvoiceLineExtracted(BaseModel):
    line_number: int = Field(..., description="Line number on the invoice")
    description: str = Field(..., description="Item description")
    quantity: float = Field(..., description="Quantity of items")
    unit_price: float = Field(..., description="Unit price of the item")
    amount: float = Field(..., description="Total amount for this line")
    tax_rate: float = Field(0.0, description="Tax rate applied to this line")
    po_line_ref: str | None = Field(None, description="Reference to the PO line number")


class ExtractedInvoice(BaseModel):
    invoice_number: str = Field(..., description="Invoice number")
    vendor_name: str | None = Field(None, description="Name of the vendor")
    vendor_id_ref: str | None = Field(None, description="Vendor reference or ID on the invoice")
    po_number: str | None = Field(None, description="Purchase order number referenced")
    total_amount: float = Field(..., description="Total amount of the invoice")
    currency: str = Field("USD", description="Currency code (e.g., USD, EUR)")
    tax_amount: float = Field(0.0, description="Total tax amount")
    line_items: list[InvoiceLineExtracted] = Field(default_factory=list, description="List of line items")
    invoice_date: str | None = Field(None, description="Date of the invoice in ISO format")
    due_date: str | None = Field(None, description="Due date in ISO format")
    payment_terms: str | None = Field(None, description="Payment terms specified")
    fields_requiring_confirmation: list[str] = Field(default_factory=list, description="Fields with low OCR confidence")


class FraudSignal(BaseModel):
    signal_type: str = Field(..., description="Type of fraud signal detected")
    description: str = Field(..., description="Description of the signal")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")


class InvoiceRiskAssessment(BaseModel):
    disposition: str = Field(..., description="Overall risk disposition (e.g., PASS, REVIEW, REJECT)")
    fraud_signals: list[FraudSignal] = Field(default_factory=list, description="List of detected fraud signals")
    duplicate_invoice_found: bool = Field(False, description="True if a duplicate invoice was found in the system")


class LineMatch(BaseModel):
    invoice_line: InvoiceLineExtracted | None = Field(None, description="The invoice line item")
    po_line: dict[str, Any] | None = Field(None, description="The matched PO line details")
    grn_line: dict[str, Any] | None = Field(None, description="The matched GRN line details")
    price_variance: float = Field(0.0, description="Absolute price variance")
    quantity_variance: float = Field(0.0, description="Absolute quantity variance")
    match_status: str = Field(..., description="FULL_MATCH, PARTIAL_MATCH, NO_MATCH, MISSING_REFERENCE")
    signals: dict[str, Any] = Field(default_factory=dict, description="Additional signals for the match")


class ThreeWayMatchResult(BaseModel):
    match_status: str = Field(..., description="Overall match status")
    line_matches: list[LineMatch] = Field(default_factory=list, description="Line-by-line matching results")
    overall_variance_amount: float = Field(0.0, description="Total absolute variance amount")
    overall_variance_pct: float = Field(0.0, description="Total percentage variance")
    unmatched_invoice_lines: list[InvoiceLineExtracted] = Field(default_factory=list)
    unmatched_po_lines: list[dict[str, Any]] = Field(default_factory=list)


class ExceptionClassification(BaseModel):
    exception_type: str = Field(..., description="Type of exception (e.g., PRICE_VARIANCE, QUANTITY_MISMATCH)")
    severity: str = Field(..., description="Severity of the exception (LOW, MEDIUM, HIGH, CRITICAL)")
    confidence: float = Field(..., description="Confidence score of the classification (0.0 to 1.0)")
    mismatch_details: dict[str, Any] = Field(default_factory=dict, description="Detailed explanation of the mismatch")
    affected_lines: list[int] = Field(default_factory=list, description="Line numbers affected by the exception")


class ToleranceResult(BaseModel):
    within_tolerance: bool = Field(..., description="True if the variance is within policy limits")
    threshold_amount: float | None = Field(None, description="Maximum allowed absolute variance amount")
    threshold_pct: float | None = Field(None, description="Maximum allowed percentage variance")
    actual_variance: float = Field(..., description="The actual computed variance amount")
    policy_ref: str | None = Field(None, description="Reference to the policy clause applied")
    exception_type: str = Field(..., description="The exception type evaluated")


class InvoiceEvidencePacket(BaseModel):
    case_id: str
    run_id: str
    recommendation: str = Field(..., description="RESOLVE_EXCEPTION, REJECT, REQUEST_INFORMATION, REVIEW_REQUIRED, ESCALATE")
    reason_codes: list[str] = Field(default_factory=list)
    extracted_invoice: ExtractedInvoice | None = None
    match_result: ThreeWayMatchResult | None = None
    exception: list[ExceptionClassification] = Field(default_factory=list)
    tolerance: ToleranceResult | None = None
    risk: InvoiceRiskAssessment | None = None
    policy_clauses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)


class InvoiceVerificationResult(BaseModel):
    passed: bool = Field(..., description="True if the evidence is complete and verified")
    blocking_reasons: list[str] = Field(default_factory=list, description="Reasons for verification failure")
    approval_role: str | None = Field(None, description="Role required for approval (e.g., finance_manager, AP_clerk)")
