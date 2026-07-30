"""Assemble everything the supplier controls need from one case.

The worker previously flattened every extracted field into a single dict keyed
by field name, first one wins. That is fine for identity fields, which every
document restates identically, but it destroys the association a certificate
check depends on: "valid until 14 January 2027" means nothing unless you know
*which* certificate said it.

So this builds a per-document view first, then derives the case-level profile
from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.domain.documents import (
    DocumentType,
    classify_document,
    questionnaire_controls,
)
from app.domain.extraction import parse_date, parse_money, parse_period
from app.domain.injection import InjectionScanResult, scan_pages
from app.models import Document, DocumentPage, ExtractedField
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_AFFIRMATIVE = {"YES", "Y", "TRUE"}
_NEGATIVE = {"NO", "N", "FALSE"}


@dataclass
class ClassifiedDocument:
    document_id: uuid.UUID
    filename: str
    document_type: DocumentType
    classification_signal: str
    pages: list[tuple[int, str]] = field(default_factory=list)
    fields: dict[str, ExtractedField] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(text for _, text in self.pages)

    def value(self, field_name: str) -> str | None:
        found = self.fields.get(field_name)
        if not found:
            return None
        return found.normalized_value or found.field_value_masked


@dataclass
class SupplierProfile:
    documents: list[ClassifiedDocument]
    injection: InjectionScanResult

    # Declared commercial profile
    annual_spend: Decimal | None = None
    spend_currency: str | None = None
    data_access_declared: bool | None = None

    # Security questionnaire answers
    data_stored_outside_country: bool | None = None
    dpa_available: bool | None = None

    # Certificate validity
    insurance_valid_from: date | None = None
    insurance_valid_to: date | None = None
    tax_certificate_valid_to: date | None = None

    @property
    def present_types(self) -> set[DocumentType]:
        return {
            document.document_type
            for document in self.documents
            if document.document_type is not DocumentType.UNKNOWN
        }

    @property
    def unclassified_count(self) -> int:
        return sum(
            1
            for document in self.documents
            if document.document_type is DocumentType.UNKNOWN
        )

    @property
    def dpa_document_present(self) -> bool:
        return DocumentType.DATA_PROCESSING_AGREEMENT in self.present_types

    def as_dict(self) -> dict[str, object]:
        return {
            "documents": [
                {
                    "document_id": str(document.document_id),
                    "filename": document.filename,
                    "document_type": str(document.document_type),
                    "classification_signal": document.classification_signal,
                }
                for document in self.documents
            ],
            "annual_spend": (
                str(self.annual_spend) if self.annual_spend is not None else None
            ),
            "spend_currency": self.spend_currency,
            "data_access_declared": self.data_access_declared,
            "data_stored_outside_country": self.data_stored_outside_country,
            "data_processing_agreement_available": self.dpa_available,
            "insurance_valid_to": (
                self.insurance_valid_to.isoformat()
                if self.insurance_valid_to
                else None
            ),
            "tax_certificate_valid_to": (
                self.tax_certificate_valid_to.isoformat()
                if self.tax_certificate_valid_to
                else None
            ),
        }


def _boolean(value: str | None) -> bool | None:
    """Read a Yes/No declaration. Unrecognised text is unknown, not False."""
    if not value:
        return None
    token = value.strip().upper().split(",")[0].strip()
    if token in _AFFIRMATIVE:
        return True
    if token in _NEGATIVE:
        return False
    return None


async def build_supplier_profile(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID,
) -> SupplierProfile:
    documents = (
        await session.execute(
            select(Document).where(
                Document.case_id == case_id, Document.tenant_id == tenant_id
            )
        )
    ).scalars().all()

    pages_by_document: dict[uuid.UUID, list[tuple[int, str]]] = {}
    for page in (
        await session.execute(
            select(DocumentPage)
            .where(DocumentPage.tenant_id == tenant_id)
            .order_by(DocumentPage.document_id, DocumentPage.page_number)
        )
    ).scalars():
        pages_by_document.setdefault(page.document_id, []).append(
            (page.page_number, page.text_content or "")
        )

    fields_by_document: dict[uuid.UUID, dict[str, ExtractedField]] = {}
    for extracted in (
        await session.execute(
            select(ExtractedField)
            .join(Document)
            .where(Document.case_id == case_id, ExtractedField.tenant_id == tenant_id)
        )
    ).scalars():
        fields_by_document.setdefault(extracted.document_id, {})[
            extracted.field_name
        ] = extracted

    classified: list[ClassifiedDocument] = []
    for document in documents:
        pages = pages_by_document.get(document.document_id, [])
        text = "\n".join(page_text for _, page_text in pages)
        document_type, signal = classify_document(document.original_filename, text)
        classified.append(
            ClassifiedDocument(
                document_id=document.document_id,
                filename=document.original_filename,
                document_type=document_type,
                classification_signal=signal,
                pages=pages,
                fields=fields_by_document.get(document.document_id, {}),
            )
        )

    profile = SupplierProfile(
        documents=classified,
        # The scan runs over every page of every document, before any model
        # call. See app/domain/injection.py.
        injection=scan_pages(
            [page for document in classified for page in document.pages]
        ),
    )
    _apply_onboarding_form(profile)
    _apply_questionnaire(profile)
    _apply_certificates(profile)
    return profile


def _document_of(
    profile: SupplierProfile, document_type: DocumentType
) -> ClassifiedDocument | None:
    return next(
        (
            document
            for document in profile.documents
            if document.document_type is document_type
        ),
        None,
    )


def _apply_onboarding_form(profile: SupplierProfile) -> None:
    form = _document_of(profile, DocumentType.SUPPLIER_ONBOARDING_FORM)
    if form is None:
        return
    currency, amount = parse_money(form.value("annual_spend"))
    profile.annual_spend = amount
    profile.spend_currency = currency
    profile.data_access_declared = _boolean(form.value("company_data_access"))


def _apply_questionnaire(profile: SupplierProfile) -> None:
    questionnaire = _document_of(profile, DocumentType.INFOSEC_QUESTIONNAIRE)
    if questionnaire is None:
        return
    controls = questionnaire_controls(questionnaire.text)
    residency = controls.get("data_stored_outside_country")
    if residency is not None:
        profile.data_stored_outside_country = residency.answer
    agreement = controls.get("data_processing_agreement_available")
    if agreement is not None:
        profile.dpa_available = agreement.answer


def _apply_certificates(profile: SupplierProfile) -> None:
    insurance = _document_of(profile, DocumentType.INSURANCE_CERTIFICATE)
    if insurance is not None:
        valid_from, valid_to = parse_period(insurance.value("insurance_period"))
        profile.insurance_valid_from = valid_from
        profile.insurance_valid_to = valid_to or parse_date(
            insurance.value("certificate_valid_until")
        )

    tax_certificate = _document_of(profile, DocumentType.TAX_REGISTRATION)
    if tax_certificate is not None:
        profile.tax_certificate_valid_to = parse_date(
            tax_certificate.value("certificate_valid_until")
        )
