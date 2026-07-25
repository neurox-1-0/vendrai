import importlib.util
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

MODULE_PATH = Path(__file__).parents[2] / "mock_erp" / "app.py"
SPEC = importlib.util.spec_from_file_location("neurox_mock_erp", MODULE_PATH)
assert SPEC and SPEC.loader
mock_erp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mock_erp)


@pytest.mark.asyncio
async def test_mock_erp_replays_identical_vendor_write_and_rejects_key_reuse(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(mock_erp, "DB_PATH", tmp_path / "erp.sqlite")
    payload = {
        "legal_name": "Synthetic Components",
        "registered_country": "XZ",
        "approval_task_id": "approval-1",
        "evidence_hash": "a" * 64,
    }
    async with AsyncClient(
        transport=ASGITransport(app=mock_erp.app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/v1/vendors",
            json=payload,
            headers={"Idempotency-Key": "vendor-operation-001"},
        )
        replay = await client.post(
            "/v1/vendors",
            json=payload,
            headers={"Idempotency-Key": "vendor-operation-001"},
        )
        conflict = await client.post(
            "/v1/vendors",
            json={**payload, "legal_name": "Different Supplier"},
            headers={"Idempotency-Key": "vendor-operation-001"},
        )
    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["erp_vendor_id"] == replay.json()["erp_vendor_id"]
    assert replay.json()["idempotent_replay"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
