from pydantic import BaseModel, Field
from typing import Optional

class SupplierDocumentFields(BaseModel):
    vendor_name: str = Field(description="The legal name of the vendor or supplier")
    tax_id: Optional[str] = Field(None, description="The VAT, EIN, or other Tax Identification Number")
    address: Optional[str] = Field(None, description="The primary registered address of the vendor")
    bank_name: Optional[str] = Field(None, description="Name of the bank where the account is held")
    bank_account_number: Optional[str] = Field(None, description="The bank account or IBAN number")
    swift_code: Optional[str] = Field(None, description="The SWIFT or BIC code of the bank")
    invoice_amount: Optional[float] = Field(None, description="The total amount of the invoice, if present")
    currency: Optional[str] = Field(None, description="The currency of the invoice, e.g. USD, EUR")

class DuplicateDecision(BaseModel):
    is_duplicate: bool = Field(description="True if the extracted vendor is highly likely a duplicate of the existing ERP vendor")
    confidence_score: float = Field(description="Confidence score from 0.0 to 1.0 that this is a duplicate")
    existing_vendor_id: Optional[str] = Field(None, description="The ERP ID of the matched vendor if a duplicate is found")
    reasoning: str = Field(description="Explanation of why this is or is not considered a duplicate based on name and tax ID matching")

class RiskAssessment(BaseModel):
    risk_level: str = Field(description="The assigned risk level: LOW, MEDIUM, or HIGH")
    risk_factors: list[str] = Field(description="List of specific risk factors identified, e.g. 'Sanctions match', 'High-risk country'")
    requires_manual_review: bool = Field(description="True if the risk level is MEDIUM or HIGH, requiring human approval")
    reasoning: str = Field(description="Detailed explanation of how the risk level was determined")

class PolicyEvaluation(BaseModel):
    policy_adherence: str = Field(description="PASS, FAIL, or REQUIRES_REVIEW based on the vendor and policies")
    policy_flags: list[str] = Field(description="List of specific policy clauses violated or flagged")
    reasoning: str = Field(description="Detailed explanation of how the vendor adheres to or violates the retrieved policies")
