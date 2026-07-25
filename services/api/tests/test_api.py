import uuid
from datetime import UTC, datetime

import pytest
from app.database import AsyncSessionLocal
from app.main import app
from app.models import AgentRun, AgentStep, ApprovalTask
from httpx import ASGITransport, AsyncClient


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


@pytest.mark.asyncio
async def test_requester_default_roles_do_not_bypass_case_ownership():
    transport = ASGITransport(app=app)
    owner_headers = {
        "X-Dev-User-Id": "00000000-0000-0000-0000-000000000301",
        "X-Dev-Roles": "requester,default-roles-neurox,offline_access",
    }
    other_requester_headers = {
        "X-Dev-User-Id": "00000000-0000-0000-0000-000000000302",
        "X-Dev-Roles": "requester,default-roles-neurox,offline_access",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases",
            json={"title": "Owner scoped case"},
            headers={
                **owner_headers,
                "Idempotency-Key": "owner-scoped-case",
            },
        )
        case_id = created.json()["case_id"]
        hidden = await client.get(
            f"/api/v1/cases/{case_id}",
            headers=other_requester_headers,
        )
        hidden_list = await client.get(
            "/api/v1/cases",
            headers=other_requester_headers,
        )
        cancel = await client.post(
            f"/api/v1/cases/{case_id}:cancel",
            headers={
                **other_requester_headers,
                "Idempotency-Key": "cross-requester-cancel",
                "If-Match": "1",
            },
        )
        initiate = await client.post(
            f"/api/v1/cases/{case_id}/documents:initiate",
            json={
                "filename": "synthetic.pdf",
                "content_type": "application/pdf",
                "size_bytes": 128,
                "document_type": "TAX_FORM",
            },
            headers={
                **other_requester_headers,
                "Idempotency-Key": "cross-requester-upload",
            },
        )
        procurement_view = await client.get(
            f"/api/v1/cases/{case_id}",
            headers={"X-Dev-Roles": "procurement_approver"},
        )
    assert hidden.status_code == 404
    assert hidden_list.json()["total"] == 0
    assert cancel.status_code == 404
    assert initiate.status_code == 404
    assert procurement_view.status_code == 200


@pytest.mark.asyncio
async def test_case_claim_is_versioned_and_cannot_be_stolen():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases",
            json={"title": "Claimed work item"},
            headers={"Idempotency-Key": "create-case-claim"},
        )
        case_id = created.json()["case_id"]
        claimed = await client.post(
            f"/api/v1/cases/{case_id}:claim",
            headers={
                "Idempotency-Key": "claim-case-one",
                "If-Match": "1",
            },
        )
        other = await client.post(
            f"/api/v1/cases/{case_id}:claim",
            headers={
                "Idempotency-Key": "claim-case-two",
                "If-Match": "2",
                "X-Dev-User-Id": (
                    "00000000-0000-0000-0000-000000000202"
                ),
                "X-Dev-Roles": "analyst",
            },
        )
        queue = await client.get("/api/v1/work-queue?ownership=MINE")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assigned_user_id"] == (
        "00000000-0000-0000-0000-000000000101"
    )
    assert other.status_code == 409
    assert other.json()["detail"]["code"] == "CASE_ALREADY_CLAIMED"
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["ownership"] == "MINE"


@pytest.mark.asyncio
async def test_approval_queues_are_scoped_to_assigned_role():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases",
            json={"title": "Role scoped approvals"},
            headers={"Idempotency-Key": "role-scoped-case"},
        )
        case_id = uuid.UUID(created.json()["case_id"])
        run_id = uuid.uuid4()
        async with AsyncSessionLocal() as session, session.begin():
            session.add(
                AgentRun(
                    run_id=run_id,
                    tenant_id=uuid.UUID(
                        "00000000-0000-0000-0000-000000000001"
                    ),
                    case_id=case_id,
                    thread_id=f"test:{run_id}",
                    graph_name="vendor_onboarding",
                    status="INTERRUPTED",
                )
            )
            for task_type, role in (
                ("VENDOR_CREATION", "procurement_approver"),
                ("INVOICE_AP_APPROVAL", "finance_approver"),
                ("BANK_CHANGE_REVIEW", "finance_approver"),
            ):
                session.add(
                    ApprovalTask(
                        tenant_id=uuid.UUID(
                            "00000000-0000-0000-0000-000000000001"
                        ),
                        case_id=case_id,
                        run_id=run_id,
                        task_type=task_type,
                        assigned_role=role,
                        evidence_hash="a" * 64,
                        case_version=1,
                    )
                )
        procurement = await client.get(
            "/api/v1/approval-tasks",
            headers={"X-Dev-Roles": "procurement_approver"},
        )
        finance = await client.get(
            "/api/v1/review-tasks",
            headers={"X-Dev-Roles": "finance_approver"},
        )
    assert [item["assigned_role"] for item in procurement.json()] == [
        "procurement_approver"
    ]
    assert [item["task_type"] for item in finance.json()] == [
        "BANK_CHANGE_REVIEW"
    ]


@pytest.mark.asyncio
async def test_run_graph_exposes_real_steps_timings_and_sanitized_diagnostics():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases",
            json={"title": "Observable supplier run"},
            headers={"Idempotency-Key": "observable-run-case"},
        )
        case_id = uuid.UUID(created.json()["case_id"])
        run_id = uuid.uuid4()
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        async with AsyncSessionLocal() as session, session.begin():
            session.add(
                AgentRun(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    thread_id=f"observable:{run_id}",
                    graph_name="vendor_onboarding",
                    graph_version="2.0.0",
                    status="RUNNING",
                    current_node="gemini_contradiction",
                    state_json={
                        "plan": {
                            "objective": "Verify a synthetic supplier.",
                            "selected_capabilities": [
                                "duplicate_detection",
                                "sanctions_screening",
                            ],
                        },
                        "evidence_hash": "a" * 64,
                        "raw_ocr": "must not be returned",
                    },
                    model_name="gemini-test",
                    prompt_version="planner-v1",
                    started_at=datetime.now(UTC),
                )
            )
            session.add_all(
                [
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name="document_intelligence",
                        attempt=1,
                        status="SUCCESS",
                        input_summary={
                            "route_reason": "Documents are ready.",
                            "bank_account": "secret",
                        },
                        output_summary={"page_count": 2},
                        error={},
                        latency_ms=120,
                    ),
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name="duplicate_detection",
                        attempt=1,
                        status="SUCCESS",
                        input_summary={
                            "dependencies": ["document_intelligence"],
                            "route_reason": "A legal name is available.",
                        },
                        output_summary={"candidate_count": 1},
                        error={},
                        latency_ms=80,
                    ),
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        node_name="sanctions_screening",
                        attempt=1,
                        status="SUCCESS",
                        input_summary={
                            "dependencies": ["document_intelligence"],
                            "route_reason": "Identity evidence is available.",
                        },
                        output_summary={"disposition": "CLEAR"},
                        error={},
                        latency_ms=90,
                    ),
                ]
            )
        graph = await client.get(f"/api/v1/runs/{run_id}/graph")
        diagnostics = await client.get(
            f"/api/v1/runs/{run_id}/diagnostics",
        )
        forbidden = await client.get(
            f"/api/v1/runs/{run_id}/diagnostics",
            headers={"X-Dev-Roles": "requester"},
        )
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert body["objective"] == "Verify a synthetic supplier."
    assert len(body["nodes"]) == 3
    assert body["timing"]["active_compute_ms"] == 290
    assert body["timing"]["critical_path_ms"] == 210
    assert body["timing"]["parallel_time_saved_ms"] == 80
    assert body["nodes"][0]["input_summary"]["bank_account"] == "<REDACTED>"
    assert diagnostics.status_code == 200
    assert diagnostics.json()["integrity"]["private_reasoning_persisted"] is False
    assert "raw_ocr" not in diagnostics.json()["decision_summary"]
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_is_authorized_hashed_and_downloadable():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/v1/cases",
            json={"title": "Auditable case"},
            headers={"Idempotency-Key": "create-audit-case"},
        )
        case_id = created.json()["case_id"]
        exported = await client.post(
            f"/api/v1/cases/{case_id}/audit-exports",
            headers={
                "Idempotency-Key": "export-audit-case",
                "If-Match": "1",
            },
        )
        downloaded = await client.get(exported.json()["download_url"])
        requester_only = await client.post(
            f"/api/v1/cases/{case_id}/audit-exports",
            headers={
                "Idempotency-Key": "unauthorized-export",
                "If-Match": "1",
                "X-Dev-Roles": "requester",
            },
        )
    assert exported.status_code == 201, exported.text
    assert len(exported.json()["sha256"]) == 64
    assert downloaded.status_code == 200
    assert downloaded.json()["case"]["case_id"] == case_id
    assert requester_only.status_code == 403


@pytest.mark.asyncio
async def test_sanctions_import_is_durable_idempotent_and_source_allowlisted():
    transport = ASGITransport(app=app)
    headers = {"Idempotency-Key": "ofac-refresh-001"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/admin/sanctions-imports",
            json={"source": "OFAC"},
            headers=headers,
        )
        replay = await client.post(
            "/api/v1/admin/sanctions-imports",
            json={"source": "OFAC"},
            headers=headers,
        )
        missing_eu = await client.post(
            "/api/v1/admin/sanctions-imports",
            json={"source": "EU"},
            headers={"Idempotency-Key": "eu-refresh-001"},
        )
    assert first.status_code == 202, first.text
    assert replay.status_code == 202, replay.text
    assert first.json()["sanctions_import_id"] == replay.json()[
        "sanctions_import_id"
    ]
    assert first.json()["status"] == "QUEUED"
    assert missing_eu.status_code == 409
    assert missing_eu.json()["detail"]["code"] == (
        "SANCTIONS_SOURCE_NOT_CONFIGURED"
    )
