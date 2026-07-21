from enum import StrEnum


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    FILE_SCANNING = "FILE_SCANNING"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    SPECIALIST_ANALYSIS = "SPECIALIST_ANALYSIS"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    DUPLICATE_REVIEW = "DUPLICATE_REVIEW"
    RISK_REVIEW = "RISK_REVIEW"
    EVIDENCE_BUILDING = "EVIDENCE_BUILDING"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ERP_SYNC_PENDING = "ERP_SYNC_PENDING"
    ERP_SYNC_FAILED = "ERP_SYNC_FAILED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    # Invoice exception statuses
    INVOICE_MATCHING = "INVOICE_MATCHING"
    EXCEPTION_CLASSIFIED = "EXCEPTION_CLASSIFIED"
    TOLERANCE_CHECK = "TOLERANCE_CHECK"
    AUTO_RESOLVED = "AUTO_RESOLVED"


ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.DRAFT: {CaseStatus.SUBMITTED, CaseStatus.CANCELLED},
    CaseStatus.SUBMITTED: {CaseStatus.FILE_SCANNING, CaseStatus.CANCELLED, CaseStatus.FAILED},
    CaseStatus.FILE_SCANNING: {CaseStatus.DOCUMENT_PROCESSING, CaseStatus.FAILED, CaseStatus.CANCELLED},
    CaseStatus.DOCUMENT_PROCESSING: {CaseStatus.SPECIALIST_ANALYSIS, CaseStatus.INVOICE_MATCHING, CaseStatus.NEEDS_CLARIFICATION, CaseStatus.FAILED, CaseStatus.CANCELLED},
    CaseStatus.SPECIALIST_ANALYSIS: {CaseStatus.NEEDS_CLARIFICATION, CaseStatus.DUPLICATE_REVIEW, CaseStatus.RISK_REVIEW, CaseStatus.EVIDENCE_BUILDING, CaseStatus.FAILED, CaseStatus.CANCELLED},
    CaseStatus.NEEDS_CLARIFICATION: {CaseStatus.DOCUMENT_PROCESSING, CaseStatus.SPECIALIST_ANALYSIS, CaseStatus.INVOICE_MATCHING, CaseStatus.CANCELLED},
    CaseStatus.DUPLICATE_REVIEW: {CaseStatus.SPECIALIST_ANALYSIS, CaseStatus.EVIDENCE_BUILDING, CaseStatus.REJECTED, CaseStatus.CANCELLED},
    CaseStatus.RISK_REVIEW: {CaseStatus.EVIDENCE_BUILDING, CaseStatus.REJECTED, CaseStatus.CANCELLED},
    CaseStatus.EVIDENCE_BUILDING: {CaseStatus.APPROVAL_PENDING, CaseStatus.VERIFICATION_FAILED, CaseStatus.FAILED},
    CaseStatus.VERIFICATION_FAILED: {CaseStatus.NEEDS_CLARIFICATION, CaseStatus.SPECIALIST_ANALYSIS, CaseStatus.CANCELLED},
    CaseStatus.APPROVAL_PENDING: {CaseStatus.APPROVED, CaseStatus.REJECTED, CaseStatus.NEEDS_CLARIFICATION, CaseStatus.CANCELLED},
    CaseStatus.APPROVED: {CaseStatus.ERP_SYNC_PENDING},
    CaseStatus.ERP_SYNC_PENDING: {CaseStatus.COMPLETED, CaseStatus.ERP_SYNC_FAILED},
    CaseStatus.ERP_SYNC_FAILED: {CaseStatus.ERP_SYNC_PENDING, CaseStatus.CANCELLED},
    CaseStatus.REJECTED: set(),
    CaseStatus.COMPLETED: set(),
    CaseStatus.FAILED: set(),
    CaseStatus.CANCELLED: set(),
    # Invoice exception transitions
    CaseStatus.INVOICE_MATCHING: {CaseStatus.EXCEPTION_CLASSIFIED, CaseStatus.NEEDS_CLARIFICATION, CaseStatus.FAILED},
    CaseStatus.EXCEPTION_CLASSIFIED: {CaseStatus.TOLERANCE_CHECK, CaseStatus.NEEDS_CLARIFICATION, CaseStatus.FAILED},
    CaseStatus.TOLERANCE_CHECK: {CaseStatus.AUTO_RESOLVED, CaseStatus.EVIDENCE_BUILDING, CaseStatus.NEEDS_CLARIFICATION},
    CaseStatus.AUTO_RESOLVED: {CaseStatus.ERP_SYNC_PENDING},
}


class InvalidTransition(ValueError):
    pass


def assert_transition(current: str, target: str) -> None:
    try:
        source_status = CaseStatus(current)
        target_status = CaseStatus(target)
    except ValueError as exc:
        raise InvalidTransition(f"Unknown case state: {exc}") from exc
    if target_status not in ALLOWED_TRANSITIONS[source_status]:
        raise InvalidTransition(f"{source_status} cannot transition to {target_status}")
