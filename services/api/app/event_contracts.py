import re
from typing import Any

EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.-]+\.v[1-9][0-9]*$")
FORBIDDEN_EVENT_KEYS = {
    "account_number",
    "answers",
    "bank_account",
    "comment",
    "document_bytes",
    "email",
    "password",
    "phone",
    "raw_document",
    "raw_ocr",
    "swift_code",
    "tax_id",
}
REQUIRED_EVENT_PAYLOADS = {
    "agent.analysis.requested.v1": {"case_id", "run_id"},
    "agent.erp.confirmed.v1": {
        "case_id",
        "run_id",
        "operation_id",
        "status",
    },
    "approval.approved.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "evidence_hash",
        "expected_version",
        "actor_id",
    },
    "approval.escalated.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "evidence_hash",
        "expected_version",
        "actor_id",
    },
    "approval.more_info.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "evidence_hash",
        "expected_version",
        "actor_id",
    },
    "approval.rejected.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "evidence_hash",
        "expected_version",
        "actor_id",
    },
    "case.submitted.v1": {"case_id", "run_id"},
    "clarification.answered.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "expected_version",
        "actor_id",
    },
    "document.processing.requested.v1": {"document_id", "case_id"},
    "erp.sync.requested.v1": {
        "case_id",
        "run_id",
        "approval_task_id",
        "evidence_hash",
    },
    "invoice.analysis.requested.v1": {"case_id", "run_id"},
    "invoice.resolution.approved.v1": {
        "case_id",
        "run_id",
        "approval_task_id",
        "evidence_hash",
    },
    "invoice.submitted.v1": {"case_id", "run_id"},
    "notification.delivery.requested.v1": {
        "notification_id",
        "attempt",
    },
    "policy.published.v1": {"policy_version_id"},
    "review.resolved.v1": {
        "case_id",
        "run_id",
        "task_id",
        "decision",
        "evidence_hash",
        "expected_version",
        "actor_id",
    },
    "sanctions.import.requested.v1": {
        "sanctions_import_id",
        "source",
    },
}


def _forbidden_paths(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_EVENT_KEYS or normalized.startswith("raw_"):
                violations.append(".".join((*path, normalized)))
            violations.extend(_forbidden_paths(child, (*path, normalized)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_forbidden_paths(child, (*path, str(index))))
    elif isinstance(value, (bytes, bytearray)):
        violations.append(".".join(path) or "<bytes>")
    return violations


def validate_event_contract(event_type: str, payload: dict[str, Any]) -> None:
    if not EVENT_TYPE.fullmatch(event_type):
        raise ValueError("EVENT_TYPE_MUST_BE_VERSIONED")
    required = REQUIRED_EVENT_PAYLOADS.get(event_type, set())
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(
            f"EVENT_PAYLOAD_INVALID:{event_type}:missing={','.join(missing)}"
        )
    violations = _forbidden_paths(payload)
    if violations:
        raise ValueError(
            "EVENT_PAYLOAD_CONTAINS_SENSITIVE_FIELDS:"
            + ",".join(sorted(set(violations))[:10])
        )
