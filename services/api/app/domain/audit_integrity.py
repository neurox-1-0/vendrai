"""Verify the audit hash chain.

Writing a hash chain is not an integrity control. **Detecting a break in it
is.** Until something recomputes the chain and reports a mismatch, the hashes
are decoration: a tampered row carries whatever hash the tamperer wrote, and
nobody looks.

This module is the detection path. It is a pure function over records so it can
be exercised against a deliberately corrupted chain in a unit test - which is
the only way to know it would catch a real one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.security import chained_audit_hash


class AuditRecordLike(Protocol):
    """Structural, so verification does not require an ORM session."""

    audit_log_id: Any
    tenant_id: Any
    case_id: Any
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata_json: dict[str, Any]
    previous_hash: str | None
    record_hash: str


class Break(str):
    """A named kind of chain failure, used in reports and assertions."""


CONTENT_ALTERED = Break("CONTENT_ALTERED")
LINK_BROKEN = Break("LINK_BROKEN")
CHAIN_ROOT_INVALID = Break("CHAIN_ROOT_INVALID")


@dataclass(frozen=True)
class ChainBreak:
    audit_log_id: str
    kind: Break
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "audit_log_id": self.audit_log_id,
            "kind": str(self.kind),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationResult:
    verified_count: int
    breaks: tuple[ChainBreak, ...] = field(default_factory=tuple)

    @property
    def intact(self) -> bool:
        return not self.breaks

    def as_dict(self) -> dict[str, Any]:
        return {
            "intact": self.intact,
            "verified_count": self.verified_count,
            "breaks": [item.as_dict() for item in self.breaks],
        }


def record_payload(record: AuditRecordLike) -> dict[str, Any]:
    """Rebuild the exact structure that was hashed at append time.

    This must stay byte-identical to what app/services/events.append_audit
    hashes. If the two drift, every record verifies as tampered and the alarm
    becomes noise nobody acts on.
    """
    return {
        "tenant_id": str(record.tenant_id),
        "case_id": str(record.case_id) if record.case_id else None,
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "action": record.action,
        "resource_type": record.resource_type,
        "resource_id": record.resource_id,
        "metadata": record.metadata_json,
    }


def verify_chain(records: list[AuditRecordLike]) -> VerificationResult:
    """Recompute the chain over records in append order.

    Reports every break rather than stopping at the first: a tamperer who
    edits one row usually edits several, and knowing the extent matters as
    much as knowing it happened.
    """
    breaks: list[ChainBreak] = []
    expected_previous: str | None = None

    for index, record in enumerate(records):
        identifier = str(record.audit_log_id)

        if record.previous_hash != expected_previous:
            breaks.append(
                ChainBreak(
                    audit_log_id=identifier,
                    kind=CHAIN_ROOT_INVALID if index == 0 else LINK_BROKEN,
                    detail=(
                        f"expected previous_hash {expected_previous!r}, "
                        f"found {record.previous_hash!r}. A record was "
                        "inserted, removed, or reordered."
                    ),
                )
            )

        recomputed = chained_audit_hash(record.previous_hash, record_payload(record))
        if recomputed != record.record_hash:
            breaks.append(
                ChainBreak(
                    audit_log_id=identifier,
                    kind=CONTENT_ALTERED,
                    detail=(
                        f"stored hash {record.record_hash} does not match the "
                        f"content, which hashes to {recomputed}."
                    ),
                )
            )
            # Continue from the stored hash so one altered record does not
            # cascade into reporting every later record as broken too.
        expected_previous = record.record_hash

    return VerificationResult(verified_count=len(records), breaks=tuple(breaks))
