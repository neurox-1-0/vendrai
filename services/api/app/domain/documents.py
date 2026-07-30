"""Classify supplier documents and decide whether the set is complete.

Two things the workflow previously could not do, and that several scenarios
depend on:

1. **Type a document.** Documents were processed without ever being
   classified, so nothing could reason about *which* documents a case held.
2. **State what a case requires.** No rule said which documents a supplier
   onboarding needs, so "required documents present" - VO-001's first expected
   finding - had nothing behind it, and VO-003's deliberately omitted tax
   registration certificate went unnoticed.

Classification is deterministic and inspectable rather than model-based. The
requirements are a declarative table rather than a chain of conditionals,
because they are policy and policy changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class DocumentType(StrEnum):
    SUPPLIER_ONBOARDING_FORM = "SUPPLIER_ONBOARDING_FORM"
    TAX_REGISTRATION = "TAX_REGISTRATION"
    BANK_CONFIRMATION = "BANK_CONFIRMATION"
    INSURANCE_CERTIFICATE = "INSURANCE_CERTIFICATE"
    INFOSEC_QUESTIONNAIRE = "INFOSEC_QUESTIONNAIRE"
    DATA_PROCESSING_AGREEMENT = "DATA_PROCESSING_AGREEMENT"
    BENEFICIAL_OWNERSHIP = "BENEFICIAL_OWNERSHIP"
    SUPPLIER_CORRESPONDENCE = "SUPPLIER_CORRESPONDENCE"
    UNKNOWN = "UNKNOWN"


DOCUMENT_LABELS: dict[DocumentType, str] = {
    DocumentType.SUPPLIER_ONBOARDING_FORM: "supplier onboarding form",
    DocumentType.TAX_REGISTRATION: "tax registration certificate",
    DocumentType.BANK_CONFIRMATION: "bank account confirmation",
    DocumentType.INSURANCE_CERTIFICATE: "insurance certificate",
    DocumentType.INFOSEC_QUESTIONNAIRE: "information security questionnaire",
    DocumentType.DATA_PROCESSING_AGREEMENT: "data processing agreement",
    DocumentType.BENEFICIAL_OWNERSHIP: "beneficial ownership declaration",
    DocumentType.SUPPLIER_CORRESPONDENCE: "supplier correspondence",
    DocumentType.UNKNOWN: "unrecognised document",
}


@dataclass(frozen=True)
class ClassificationRule:
    document_type: DocumentType
    #: Matched against the document's title heading, which is the strongest
    #: single signal and the one least affected by OCR noise elsewhere.
    title_patterns: tuple[re.Pattern[str], ...]
    #: Matched against the filename, for scans whose heading did not survive.
    filename_patterns: tuple[re.Pattern[str], ...] = ()
    #: Distinctive phrases from the body, used only when neither above matches.
    content_markers: tuple[str, ...] = ()


def _title(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.I) for pattern in patterns)


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        DocumentType.SUPPLIER_ONBOARDING_FORM,
        _title(r"^supplier\s+onboarding\s+form$", r"^vendor\s+registration\s+form$"),
        _title(r"onboarding[_-]?form", r"supplier[_-]?form"),
        ("organisation details", "commercial and banking profile"),
    ),
    ClassificationRule(
        DocumentType.TAX_REGISTRATION,
        _title(r"^tax\s+registration\s+certificate$", r"^certificate\s+of\s+tax\s+registration$"),
        _title(r"tax[_-]?registration"),
        ("tax identification number", "registrar - business tax"),
    ),
    ClassificationRule(
        DocumentType.BANK_CONFIRMATION,
        _title(r"^bank\s+account\s+confirmation$", r"^bank\s+confirmation\s+letter$"),
        _title(r"bank[_-]?(account[_-]?)?confirmation"),
        ("account is maintained with", "account holder"),
    ),
    ClassificationRule(
        DocumentType.INSURANCE_CERTIFICATE,
        _title(r"^certificate\s+of\s+insurance$", r"^insurance\s+certificate$"),
        _title(r"insurance[_-]?certificate"),
        ("limit of indemnity", "period of insurance"),
    ),
    ClassificationRule(
        DocumentType.INFOSEC_QUESTIONNAIRE,
        _title(
            r"^supplier\s+information\s+security$",
            r"^supplier\s+information\s+security\s+questionnaire$",
            r"^information\s+security\s+questionnaire$",
        ),
        _title(r"information[_-]?security", r"infosec"),
        ("information security management framework", "control question"),
    ),
    ClassificationRule(
        DocumentType.DATA_PROCESSING_AGREEMENT,
        _title(r"^data\s+processing\s+agreement$", r"^data\s+protection\s+agreement$"),
        _title(r"data[_-]?processing[_-]?agreement", r"\bdpa\b"),
        ("processes personal data on behalf of", "data processing agreement"),
    ),
    ClassificationRule(
        DocumentType.BENEFICIAL_OWNERSHIP,
        _title(r"^beneficial\s+ownership\s+declaration$"),
        _title(r"beneficial[_-]?ownership"),
        ("declared beneficial owner", "politically exposed person"),
    ),
    ClassificationRule(
        DocumentType.SUPPLIER_CORRESPONDENCE,
        _title(r"^supplier\s+correspondence$"),
        _title(r"instruction[_-]?note", r"correspondence"),
        ("supplier correspondence",),
    ),
)


def classify_document(filename: str, text: str) -> tuple[DocumentType, str]:
    """Return the document's type and the signal that decided it.

    Returning the signal matters: an operator questioning a completeness
    finding needs to see *why* a document was typed the way it was, and a
    misclassification then has an obvious place to look.
    """
    headings = _headings(text)
    for rule in CLASSIFICATION_RULES:
        for pattern in rule.title_patterns:
            if any(pattern.match(heading) for heading in headings):
                return rule.document_type, f"title heading matched {pattern.pattern}"

    lowered_name = filename.lower()
    for rule in CLASSIFICATION_RULES:
        for pattern in rule.filename_patterns:
            if pattern.search(lowered_name):
                return rule.document_type, f"filename matched {pattern.pattern}"

    lowered_text = text.lower()
    for rule in CLASSIFICATION_RULES:
        for marker in rule.content_markers:
            if marker in lowered_text:
                return rule.document_type, f"content marker {marker!r}"

    return DocumentType.UNKNOWN, "no classification signal matched"


def _headings(text: str) -> list[str]:
    """Candidate title lines: the upper-case headings near the top of a page.

    Bounded to the opening lines because that is where a document states what
    it is; scanning further finds section headings inside the body.
    """
    headings: list[str] = []
    for line in text.splitlines()[:40]:
        candidate = " ".join(line.split())
        if len(candidate) < 4 or candidate != candidate.upper():
            continue
        headings.append(candidate.strip(":."))
    # Corpus questionnaires wrap their heading across two lines; join adjacent
    # pairs so "SUPPLIER INFORMATION SECURITY" / "QUESTIONNAIRE" is findable.
    joined = [
        f"{first} {second}"
        for first, second in zip(headings, headings[1:], strict=False)
    ]
    return headings + joined


# --- Required-document matrix ----------------------------------------------


class RequirementCondition(StrEnum):
    ALWAYS = "always"
    DATA_ACCESS_DECLARED = "data_access_declared"
    DATA_STORED_OUTSIDE_COUNTRY = "data_stored_outside_country"
    SPEND_ABOVE_THRESHOLD = "spend_above_threshold"


@dataclass(frozen=True)
class DocumentRequirement:
    document_type: DocumentType
    required_when: RequirementCondition
    #: Shown to the requester when the document is missing.
    reason: str


# Versioned so a change to the matrix is visible in the evidence trail rather
# than silently altering what past cases were judged against.
REQUIREMENTS_VERSION = "1.0.0"

SUPPLIER_REQUIREMENTS: tuple[DocumentRequirement, ...] = (
    DocumentRequirement(
        DocumentType.SUPPLIER_ONBOARDING_FORM,
        RequirementCondition.ALWAYS,
        "Every supplier must submit a completed onboarding form.",
    ),
    DocumentRequirement(
        DocumentType.TAX_REGISTRATION,
        RequirementCondition.ALWAYS,
        "Current tax registration evidence is required before activation.",
    ),
    DocumentRequirement(
        DocumentType.BANK_CONFIRMATION,
        RequirementCondition.ALWAYS,
        "Bank details must be confirmed by the bank, not asserted by the supplier alone.",
    ),
    DocumentRequirement(
        DocumentType.INSURANCE_CERTIFICATE,
        RequirementCondition.ALWAYS,
        "Insurance evidence is required where the category creates operational or professional exposure.",
    ),
    DocumentRequirement(
        DocumentType.INFOSEC_QUESTIONNAIRE,
        RequirementCondition.DATA_ACCESS_DECLARED,
        "The supplier declared access to company data, which requires a completed security questionnaire.",
    ),
    DocumentRequirement(
        DocumentType.DATA_PROCESSING_AGREEMENT,
        RequirementCondition.DATA_STORED_OUTSIDE_COUNTRY,
        "Company data will be stored outside the approved locations, which requires contractual data-processing terms.",
    ),
    DocumentRequirement(
        DocumentType.BENEFICIAL_OWNERSHIP,
        RequirementCondition.SPEND_ABOVE_THRESHOLD,
        "Spend above the elevated-review threshold requires a beneficial ownership declaration.",
    ),
)


# --- Security questionnaire responses --------------------------------------

# The controls that other checks depend on. Matching is on a distinctive
# phrase from the question rather than its number, because questionnaires get
# renumbered and a question's meaning is what matters.
QUESTIONNAIRE_CONTROLS: dict[str, re.Pattern[str]] = {
    "data_stored_outside_country": re.compile(
        r"stored?\s+outside|hosted?\s+outside|data\s+residency", re.I
    ),
    "data_processing_agreement_available": re.compile(
        r"data\s+processing\s+agreement", re.I
    ),
    "subcontractors_process_data": re.compile(
        r"subcontractors?\s+process", re.I
    ),
    "data_encrypted": re.compile(r"encrypted\s+in\s+transit|encryption", re.I),
    "security_framework": re.compile(
        r"information\s+security\s+management\s+framework", re.I
    ),
}

_AFFIRMATIVE = {"yes", "y", "true"}
_NEGATIVE = {"no", "n", "false", "not available", "none"}


@dataclass(frozen=True)
class QuestionnaireResponse:
    number: int | None
    question: str
    answer: bool | None
    raw_answer: str
    details: str = ""


def extract_questionnaire_responses(text: str) -> list[QuestionnaireResponse]:
    """Parse a numbered question / Yes-No / details table.

    A standalone Yes or No line terminates the question and opens the details,
    which is what makes wrapped questions and wrapped details unambiguous
    without needing column geometry.
    """
    lines = [" ".join(line.split()) for line in text.splitlines()]
    responses: list[QuestionnaireResponse] = []
    index = 0
    while index < len(lines):
        if not re.fullmatch(r"\d{1,2}", lines[index]):
            index += 1
            continue
        number = int(lines[index])
        index += 1

        question_parts: list[str] = []
        raw_answer = ""
        while index < len(lines):
            candidate = lines[index]
            index += 1
            if not candidate:
                continue
            if candidate.lower().strip(".") in _AFFIRMATIVE | _NEGATIVE:
                raw_answer = candidate
                break
            if re.fullmatch(r"\d{1,2}", candidate):
                # Next row started without an answer; abandon this one.
                index -= 1
                break
            question_parts.append(candidate)
        if not raw_answer or not question_parts:
            continue

        detail_parts: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            if re.fullmatch(r"\d{1,2}", candidate) or candidate.startswith("____"):
                break
            index += 1
            if candidate:
                detail_parts.append(candidate)

        normalized = raw_answer.lower().strip(".")
        responses.append(
            QuestionnaireResponse(
                number=number,
                question=" ".join(question_parts),
                answer=(
                    True
                    if normalized in _AFFIRMATIVE
                    else False
                    if normalized in _NEGATIVE
                    else None
                ),
                raw_answer=raw_answer,
                details=" ".join(detail_parts),
            )
        )
    return responses


def questionnaire_controls(text: str) -> dict[str, QuestionnaireResponse]:
    """Map each known control to the response that answers it, if any.

    A control with no matching question is simply absent from the result.
    Callers must treat absence as unknown, never as a negative answer - "we
    did not ask" and "they said no" are different findings.
    """
    found: dict[str, QuestionnaireResponse] = {}
    for response in extract_questionnaire_responses(text):
        for control, pattern in QUESTIONNAIRE_CONTROLS.items():
            if control not in found and pattern.search(response.question):
                found[control] = response
    return found


@dataclass(frozen=True)
class MissingDocument:
    document_type: DocumentType
    reason: str

    @property
    def label(self) -> str:
        return DOCUMENT_LABELS[self.document_type]


@dataclass(frozen=True)
class CompletenessResult:
    disposition: str  # COMPLETE | MISSING_REQUIRED
    present: tuple[DocumentType, ...]
    missing: tuple[MissingDocument, ...] = ()
    unclassified_count: int = 0
    requirements_version: str = REQUIREMENTS_VERSION
    applied_conditions: dict[str, bool] = field(default_factory=dict)

    @property
    def reason_codes(self) -> list[str]:
        if not self.missing:
            return []
        return ["MISSING_REQUIRED_DOCUMENT"]


def evaluate_completeness(
    present: set[DocumentType],
    *,
    data_access_declared: bool,
    data_stored_outside_country: bool,
    spend_above_threshold: bool,
    unclassified_count: int = 0,
) -> CompletenessResult:
    """Decide whether the submitted set satisfies the requirements matrix."""
    conditions = {
        RequirementCondition.ALWAYS: True,
        RequirementCondition.DATA_ACCESS_DECLARED: data_access_declared,
        RequirementCondition.DATA_STORED_OUTSIDE_COUNTRY: data_stored_outside_country,
        RequirementCondition.SPEND_ABOVE_THRESHOLD: spend_above_threshold,
    }
    missing = tuple(
        MissingDocument(requirement.document_type, requirement.reason)
        for requirement in SUPPLIER_REQUIREMENTS
        if conditions[requirement.required_when]
        and requirement.document_type not in present
    )
    return CompletenessResult(
        disposition="COMPLETE" if not missing else "MISSING_REQUIRED",
        present=tuple(sorted(present, key=str)),
        missing=missing,
        unclassified_count=unclassified_count,
        applied_conditions={
            condition.value: value for condition, value in conditions.items()
        },
    )
