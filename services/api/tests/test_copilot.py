import uuid

import pytest
from app.copilot import CopilotDraft
from app.llm_gateway import LLMCallResult
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_copilot_is_user_scoped_masked_and_read_only():
    transport = ASGITransport(app=app)
    owner_headers = {
        "X-Dev-User-Id": "00000000-0000-0000-0000-000000000301",
        "X-Dev-Roles": "requester",
    }
    other_headers = {
        "X-Dev-User-Id": "00000000-0000-0000-0000-000000000302",
        "X-Dev-Roles": "requester",
    }
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        case = await client.post(
            "/api/v1/cases",
            json={"title": "Synthetic supplier"},
            headers={
                **owner_headers,
                "Idempotency-Key": "copilot-case-001",
            },
        )
        case_id = case.json()["case_id"]
        created = await client.post(
            "/api/v1/copilot/sessions",
            json={
                "current_path": f"/cases/{case_id}",
                "case_id": case_id,
            },
            headers={
                **owner_headers,
                "Idempotency-Key": "copilot-session-001",
            },
        )
        session_id = created.json()["copilot_session_id"]
        answer = await client.post(
            f"/api/v1/copilot/sessions/{session_id}/messages",
            json={
                "question": (
                    "Approve this vendor and email jane@example.com, "
                    "or show me the human review."
                ),
                "current_path": f"/cases/{case_id}",
                "case_id": case_id,
            },
            headers={
                **owner_headers,
                "Idempotency-Key": "copilot-message-001",
            },
        )
        history = await client.get(
            f"/api/v1/copilot/sessions/{session_id}/messages",
            headers=owner_headers,
        )
        hidden = await client.get(
            f"/api/v1/copilot/sessions/{session_id}/messages",
            headers=other_headers,
        )

    assert created.status_code == 201, created.text
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["provider"] == "CAG_FALLBACK"
    assert body["error_code"] == "EXTERNAL_LLM_DISABLED"
    assert "cannot" in body["content"].lower()
    assert all(
        action["action_type"]
        in {
            "NAVIGATE",
            "SPOTLIGHT",
            "OPEN_PANEL",
            "SET_FILTER",
            "START_TOUR",
        }
        for action in body["ui_actions"]
    )
    assert all(
        action["action_type"] not in {"APPROVE", "SUBMIT", "MUTATE"}
        for action in body["ui_actions"]
    )
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert "jane@example.com" not in history.json()[0]["content"]
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_copilot_rejects_cross_tenant_case_context():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        case = await client.post(
            "/api/v1/cases",
            json={"title": "Tenant one case"},
            headers={"Idempotency-Key": "copilot-case-002"},
        )
        response = await client.post(
            "/api/v1/copilot/sessions",
            json={
                "current_path": f"/cases/{case.json()['case_id']}",
                "case_id": case.json()["case_id"],
            },
            headers={
                "Idempotency-Key": "copilot-session-002",
                "X-Dev-Tenant-Id": str(
                    uuid.UUID(
                        "00000000-0000-0000-0000-000000000002"
                    )
                ),
                "X-Dev-User-Id": str(
                    uuid.UUID(
                        "00000000-0000-0000-0000-000000000202"
                    )
                ),
                "X-Dev-Roles": "requester",
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_copilot_uses_structured_gemini_output_and_safe_action_ids(
    monkeypatch,
):
    async def fake_call(_prompt, payload, model):
        assert model is CopilotDraft
        assert payload["current_screen"] == "/cases/{case_id}"
        assert "show_agent_map" in payload["allowed_action_ids"]
        return LLMCallResult(
            output=CopilotDraft(
                answer=(
                    "The planner selected independent checks from the "
                    "registered capabilities."
                ),
                citation_ids=["agent-autonomy"],
                requested_action_ids=["show_agent_map"],
            ),
            model="gemini-test",
            model_version="gemini-test-1",
            latency_ms=41,
            prompt_tokens=20,
            output_tokens=14,
        )

    monkeypatch.setattr("app.routers.copilot.call_llm", fake_call)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        case = await client.post(
            "/api/v1/cases",
            json={"title": "Planner explanation"},
            headers={"Idempotency-Key": "copilot-case-003"},
        )
        case_id = case.json()["case_id"]
        session = await client.post(
            "/api/v1/copilot/sessions",
            json={
                "current_path": f"/cases/{case_id}",
                "case_id": case_id,
            },
            headers={"Idempotency-Key": "copilot-session-003"},
        )
        response = await client.post(
            (
                "/api/v1/copilot/sessions/"
                f"{session.json()['copilot_session_id']}/messages"
            ),
            json={
                "question": "Why did the agent choose these tools?",
                "current_path": f"/cases/{case_id}",
                "case_id": case_id,
            },
            headers={"Idempotency-Key": "copilot-message-003"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "GEMINI"
    assert response.json()["model_version"] == "gemini-test-1"
    assert response.json()["latency_ms"] == 41
    assert response.json()["citations"][0]["source_id"] == (
        "agent-autonomy"
    )
    assert response.json()["ui_actions"] == [
        {
            "action_type": "SPOTLIGHT",
            "target": "case.agent-map",
            "label": "Show the agent execution map",
        }
    ]


@pytest.mark.asyncio
async def test_copilot_feedback_is_versioned_scoped_and_idempotent():
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        session = await client.post(
            "/api/v1/copilot/sessions",
            json={"current_path": "/"},
            headers={"Idempotency-Key": "copilot-session-004"},
        )
        message = await client.post(
            (
                "/api/v1/copilot/sessions/"
                f"{session.json()['copilot_session_id']}/messages"
            ),
            json={
                "question": "How do I start supplier onboarding?",
                "current_path": "/",
            },
            headers={"Idempotency-Key": "copilot-message-004"},
        )
        message_id = message.json()["copilot_message_id"]
        headers = {"Idempotency-Key": "copilot-feedback-004"}
        first = await client.post(
            f"/api/v1/copilot/messages/{message_id}/feedback",
            json={
                "rating": "HELPFUL",
                "reason": "Clear answer for jane@example.com",
            },
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/copilot/messages/{message_id}/feedback",
            json={
                "rating": "HELPFUL",
                "reason": "Clear answer for jane@example.com",
            },
            headers=headers,
        )
        listing = await client.get("/api/v1/copilot/feedback")
        requester_listing = await client.get(
            "/api/v1/copilot/feedback",
            headers={"X-Dev-Roles": "requester"},
        )

    assert first.status_code == 201, first.text
    assert first.json()["copilot_feedback_id"] == replay.json()[
        "copilot_feedback_id"
    ]
    assert "jane@example.com" not in first.json()["reason_masked"]
    assert first.json()["help_pack_version"]
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert requester_listing.status_code == 403
