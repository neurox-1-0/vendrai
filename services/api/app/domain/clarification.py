"""Turn structured findings into clarification questions a person can act on.

The old questions were templates over field names: "Please confirm or provide
legal name." That tells a requester what is missing but not why, where, or what
would resolve it - and for a case blocked on a missing certificate or a
cross-border bank account, it does not even identify the right document.

The rule that makes this trustworthy: **the set of questions comes from
deterministic findings, never from a model deciding what is missing.** A model
may rephrase a question; it may not invent one, and it may not omit one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.documents import DOCUMENT_LABELS, CompletenessResult, DocumentType


@dataclass(frozen=True)
class ClarificationQuestion:
    #: What the answer resolves - a field name, a document type, or a control.
    subject: str
    question: str
    reason_code: str
    #: Where the reviewer or requester should look. Empty when not applicable.
    locator: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "field": self.subject,
            "question": self.question,
            "reason_code": self.reason_code,
            "locator": self.locator,
        }


def for_missing_documents(
    completeness: CompletenessResult,
) -> list[ClarificationQuestion]:
    return [
        ClarificationQuestion(
            subject=str(missing.document_type),
            question=(
                f"Please upload the {missing.label}. {missing.reason}"
            ),
            reason_code="MISSING_REQUIRED_DOCUMENT",
        )
        for missing in completeness.missing
    ]


def for_low_confidence_field(
    field_name: str,
    *,
    page: int | None,
    document_label: str | None = None,
) -> ClarificationQuestion:
    readable = field_name.replace("_", " ")
    where = f" on page {page}" if page else ""
    document = f" of the {document_label}" if document_label else ""
    return ClarificationQuestion(
        subject=field_name,
        question=(
            f"The {readable}{where}{document} could not be read reliably. "
            "Please upload a clearer scan, or confirm the correct value."
        ),
        reason_code="LOW_EXTRACTION_CONFIDENCE",
        locator={"field": field_name, "page": page},
    )


def for_missing_field(field_name: str) -> ClarificationQuestion:
    readable = field_name.replace("_", " ")
    return ClarificationQuestion(
        subject=field_name,
        question=f"The {readable} was not stated on any submitted document. Please provide it.",
        reason_code="FIELD_NOT_STATED",
        locator={"field": field_name},
    )


#: One question per control reason code. Each names the specific condition, so
#: the requester knows what to send rather than being told to "complete
#: verification".
_CONTROL_QUESTIONS: dict[str, str] = {
    "BANKING_COUNTRY_MISMATCH": (
        "The bank account is held in {bank_country} but the entity is "
        "registered in {registered_country}. Please confirm this is correct "
        "and explain why payment is made to another jurisdiction."
    ),
    "BANK_BENEFICIARY_MISMATCH": (
        "The bank beneficiary name does not match the legal supplier name. "
        "Please provide a bank confirmation in the name of the registered "
        "entity, or explain the difference."
    ),
    "BANK_BENEFICIARY_IS_INDIVIDUAL": (
        "The bank account appears to be held by an individual rather than the "
        "supplier company. Please confirm the account holder and provide "
        "written authorisation from the entity."
    ),
    "DPA_UNAVAILABLE": (
        "This supplier will access company data, and has stated that no data "
        "processing agreement is currently available. Please attach the "
        "signed agreement before onboarding can continue."
    ),
    "DPA_UNVERIFIED": (
        "This supplier will access company data. Please attach the signed "
        "data processing agreement, or confirm in writing that none is required."
    ),
    "DATA_STORED_OUTSIDE_APPROVED_LOCATION": (
        "The supplier has stated that company data will be stored outside the "
        "approved locations. Please confirm the storage locations and attach "
        "the supporting transfer arrangements."
    ),
    "DATA_RESIDENCY_UNSTATED": (
        "The supplier will access company data but has not stated where that "
        "data will be stored. Please complete the data residency section of "
        "the security questionnaire."
    ),
    "CERTIFICATE_EXPIRED": (
        "A submitted certificate has expired. Please upload a current one."
    ),
    "CERTIFICATE_NOT_YET_EFFECTIVE": (
        "A submitted certificate is not yet in force. Please confirm the "
        "cover in place today."
    ),
    "CERTIFICATE_VALIDITY_UNSTATED": (
        "A submitted certificate does not state its validity period. Please "
        "upload a version showing the cover dates."
    ),
    "SPEND_CURRENCY_MISMATCH": (
        "Declared annual spend is stated in a currency the approval bands are "
        "not configured for. Please restate the estimated annual spend."
    ),
    "UNTRUSTED_DOCUMENT_INSTRUCTION": (
        "A submitted document contains text instructing that approval "
        "requirements be bypassed. That instruction has not been acted on. "
        "Please confirm the document's origin and resubmit it without "
        "processing instructions."
    ),
    "RISK_SERVICE_UNAVAILABLE": (
        "The external risk screening service did not return a result for this "
        "supplier, so screening is incomplete. Please re-run the check, or "
        "record a manual screening result."
    ),
    "ADVERSE_MEDIA_POSSIBLE_MATCH": (
        "External screening returned a possible adverse-media match for this "
        "supplier name. Please review the match and record a decision."
    ),
}


def for_control_finding(
    reason_code: str,
    evidence: dict[str, object] | None = None,
) -> ClarificationQuestion | None:
    template = _CONTROL_QUESTIONS.get(reason_code)
    if template is None:
        return None
    context = {
        "bank_country": "another country",
        "registered_country": "its home country",
        **{key: value for key, value in (evidence or {}).items() if value},
    }
    try:
        question = template.format(**context)
    except (KeyError, IndexError):
        # A template referencing evidence this finding did not carry is a bug,
        # but a missing question is worse than a slightly generic one.
        question = template
    return ClarificationQuestion(
        subject=reason_code.lower(),
        question=question,
        reason_code=reason_code,
        locator=dict(evidence or {}),
    )


def build_questions(
    *,
    completeness: CompletenessResult | None = None,
    control_reason_codes: list[str] | None = None,
    control_evidence: dict[str, dict[str, object]] | None = None,
    low_confidence_fields: list[tuple[str, int | None]] | None = None,
    missing_fields: list[str] | None = None,
) -> list[ClarificationQuestion]:
    """Assemble the full question set, de-duplicated and ordered.

    Order is deliberate: missing documents first (they unblock the most),
    then unreadable evidence, then control questions.
    """
    questions: list[ClarificationQuestion] = []
    if completeness is not None:
        questions.extend(for_missing_documents(completeness))
    for field_name, page in low_confidence_fields or []:
        questions.append(for_low_confidence_field(field_name, page=page))
    for field_name in missing_fields or []:
        questions.append(for_missing_field(field_name))
    for reason_code in control_reason_codes or []:
        question = for_control_finding(
            reason_code, (control_evidence or {}).get(reason_code)
        )
        if question is not None:
            questions.append(question)

    seen: set[str] = set()
    unique: list[ClarificationQuestion] = []
    for question in questions:
        key = f"{question.reason_code}:{question.subject}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(question)
    return unique


def document_label(document_type: DocumentType) -> str:
    return DOCUMENT_LABELS[document_type]
