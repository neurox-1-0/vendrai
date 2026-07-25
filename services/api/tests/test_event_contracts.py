import json
from pathlib import Path

import pytest
from app.event_contracts import (
    REQUIRED_EVENT_PAYLOADS,
    validate_event_contract,
)
from app.workers.outbox import REQUIRED_ROUTED_EVENTS

ROOT = Path(__file__).parents[3]


def test_all_required_routed_events_have_runtime_payload_contracts():
    assert REQUIRED_ROUTED_EVENTS == set(REQUIRED_EVENT_PAYLOADS)


def test_event_contract_rejects_unversioned_missing_and_sensitive_payloads():
    with pytest.raises(ValueError, match="VERSIONED"):
        validate_event_contract("case.submitted", {})
    with pytest.raises(ValueError, match="missing=run_id"):
        validate_event_contract("case.submitted.v1", {"case_id": "case"})
    with pytest.raises(ValueError, match="SENSITIVE"):
        validate_event_contract(
            "case.created.v1",
            {"case_id": "case", "tax_id": "forbidden"},
        )


def test_event_json_schemas_are_committed_and_parseable():
    for filename in ("envelope.schema.json", "payloads.schema.json"):
        document = json.loads(
            (ROOT / "packages" / "contracts" / "events" / filename).read_text()
        )
        assert document["$schema"].endswith("2020-12/schema")
