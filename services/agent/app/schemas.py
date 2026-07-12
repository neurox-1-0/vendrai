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
