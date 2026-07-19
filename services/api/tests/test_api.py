import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_create_is_idempotent_and_tenant_scoped():
    transport = ASGITransport(app=app)
    headers = {"Idempotency-Key": "create-case-001"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/cases", json={"title": "Onboard Acme"}, headers=headers)
        second = await client.post("/api/v1/cases", json={"title": "Ignored duplicate payload"}, headers=headers)
        listing = await client.get("/api/v1/cases")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["case_id"] == second.json()["case_id"]
    assert listing.json()["total"] == 1


@pytest.mark.asyncio
async def test_submit_requires_document():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases", json={"title": "Missing evidence"}, headers={"Idempotency-Key": "create-case-002"}
        )
        submitted = await client.post(
            f"/api/v1/cases/{created.json()['case_id']}:submit", headers={"Idempotency-Key": "submit-case-002", "If-Match": "1"}
        )
    assert submitted.status_code == 409
    assert submitted.json()["detail"]["code"] == "DOCUMENT_REQUIRED"


@pytest.mark.asyncio
async def test_cross_tenant_case_is_not_visible():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases", json={"title": "Tenant one case"}, headers={"Idempotency-Key": "create-case-003"}
        )
        other_headers = {
            "X-Dev-Tenant-Id": str(uuid.UUID("00000000-0000-0000-0000-000000000002")),
            "X-Dev-User-Id": str(uuid.UUID("00000000-0000-0000-0000-000000000202")),
        }
        hidden = await client.get(f"/api/v1/cases/{created.json()['case_id']}", headers=other_headers)
    assert hidden.status_code == 404
