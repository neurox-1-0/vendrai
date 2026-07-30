"""Audit chain verification, tested against deliberately tampered chains.

Every test here corrupts the chain on purpose. That is the only way to know the
detection path works - a verifier that has only ever seen intact data has not
been tested, it has been exercised.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.audit_integrity import (
    CHAIN_ROOT_INVALID,
    CONTENT_ALTERED,
    LINK_BROKEN,
    record_payload,
    verify_chain,
)
from app.domain.security import chained_audit_hash


@dataclass
class Record:
    action: str
    tenant_id: uuid.UUID
    audit_log_id: uuid.UUID = field(default_factory=uuid.uuid4)
    case_id: uuid.UUID | None = None
    actor_type: str = "USER"
    actor_id: str = "actor-1"
    resource_type: str = "CASE"
    resource_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    previous_hash: str | None = None
    record_hash: str = ""


def build_chain(actions: list[str]) -> list[Record]:
    """Build a genuine chain the way append_audit does."""
    tenant_id = uuid.uuid4()
    records: list[Record] = []
    previous: str | None = None
    for action in actions:
        record = Record(action=action, tenant_id=tenant_id, previous_hash=previous)
        record.record_hash = chained_audit_hash(previous, record_payload(record))
        records.append(record)
        previous = record.record_hash
    return records


def test_an_intact_chain_verifies():
    result = verify_chain(build_chain(["CASE_CREATED", "CASE_SUBMITTED", "APPROVED"]))
    assert result.intact
    assert result.verified_count == 3
    assert result.breaks == ()


def test_an_empty_chain_is_intact():
    result = verify_chain([])
    assert result.intact
    assert result.verified_count == 0


def test_altering_a_record_is_detected():
    """The classic attack: change what an entry says and leave its hash."""
    chain = build_chain(["CASE_CREATED", "APPROVED", "ERP_SYNC_QUEUED"])
    chain[1].action = "REJECTED"

    result = verify_chain(chain)
    assert not result.intact
    kinds = [item.kind for item in result.breaks]
    assert CONTENT_ALTERED in kinds
    assert result.breaks[0].audit_log_id == str(chain[1].audit_log_id)


def test_altering_metadata_is_detected():
    chain = build_chain(["APPROVAL_DECIDED"])
    chain[0].metadata_json = {"decision": "APPROVED"}
    assert not verify_chain(chain).intact


def test_deleting_a_record_breaks_the_link():
    """Removing an inconvenient entry is as much a tamper as editing one."""
    chain = build_chain(["CASE_CREATED", "SANCTIONS_REVIEW", "APPROVED"])
    without_middle = [chain[0], chain[2]]

    result = verify_chain(without_middle)
    assert not result.intact
    assert LINK_BROKEN in [item.kind for item in result.breaks]


def test_reordering_records_is_detected():
    chain = build_chain(["CASE_CREATED", "APPROVED", "ERP_SYNC_QUEUED"])
    reordered = [chain[0], chain[2], chain[1]]
    assert not verify_chain(reordered).intact


def test_a_forged_first_record_is_detected():
    chain = build_chain(["CASE_CREATED", "APPROVED"])
    chain[0].previous_hash = "forged"

    result = verify_chain(chain)
    assert not result.intact
    assert CHAIN_ROOT_INVALID in [item.kind for item in result.breaks]


def test_one_altered_record_does_not_cascade_into_every_later_record():
    """A single tamper should read as one break, not fifty.

    Reporting every subsequent record as broken buries the one that actually
    changed, which is the thing an investigator needs to find.
    """
    chain = build_chain([f"ACTION_{index}" for index in range(6)])
    chain[2].action = "TAMPERED"

    breaks = verify_chain(chain).breaks
    altered = [item for item in breaks if item.kind == CONTENT_ALTERED]
    assert len(altered) == 1
    assert altered[0].audit_log_id == str(chain[2].audit_log_id)


def test_a_break_names_the_record_and_says_what_is_wrong():
    chain = build_chain(["CASE_CREATED"])
    chain[0].action = "SOMETHING_ELSE"
    breaks = verify_chain(chain).breaks

    assert breaks[0].audit_log_id == str(chain[0].audit_log_id)
    assert "does not match the content" in breaks[0].detail
    assert breaks[0].as_dict()["kind"] == "CONTENT_ALTERED"


def test_the_hashed_payload_shape_is_pinned():
    """If this drifts from append_audit, every record verifies as tampered.

    The alarm would then be permanent noise, and a real tamper would be
    indistinguishable from the bug.
    """
    record = build_chain(["CASE_CREATED"])[0]
    assert set(record_payload(record)) == {
        "tenant_id",
        "case_id",
        "actor_type",
        "actor_id",
        "action",
        "resource_type",
        "resource_id",
        "metadata",
    }
