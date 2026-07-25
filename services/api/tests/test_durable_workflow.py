import pytest
from app.agents.contracts import ContradictionAnalysis, EvidenceCritique
from app.agents.workflow import build_workflow, workflow_config
from app.domain.security import canonical_hash
from app.llm_gateway import LLMCallResult, validate_minimized_payload
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def _state(*, gate: str = "APPROVAL") -> dict:
    packet = {
        "_data_classification": "SYNTHETIC",
        "recommendation": "CREATE_VENDOR",
        "reason_codes": [],
        "unresolved_items": [],
        "deterministic_checks": {
            "sanctions": "CLEAR",
            "duplicate": "CLEAR",
        },
        "evidence": [
            {
                "evidence_id": "ev-1",
                "source_type": "POLICY",
                "reason_code": "POLICY_CLAUSE",
                "tokenized_claim": "Approval is required.",
            }
        ],
        "policy_citations": ["SYN-PROC-001:v1:4.2"],
    }
    evidence_hash = canonical_hash(packet)
    packet["packet_hash"] = evidence_hash
    return {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "case_id": "00000000-0000-0000-0000-000000000201",
        "run_id": "00000000-0000-0000-0000-000000000301",
        "workflow_kind": "supplier",
        "evidence_hash": evidence_hash,
        "case_version": 4,
        "human_gate_kind": gate,
        "deterministic_packet": packet,
        "current_stage": "deterministic_checks_complete",
    }


@pytest.mark.asyncio
async def test_approval_and_erp_are_two_durable_interrupts(monkeypatch):
    async def fake_reasoning(_prompt, _payload, model):
        output = (
            ContradictionAnalysis(
                contradictions=[],
                clarification_questions=[],
                explanation="No contradiction in supplied evidence.",
            )
            if model is ContradictionAnalysis
            else EvidenceCritique(
                completeness_score=1,
                unsupported_claims=[],
                cited_evidence_ids=["ev-1"],
                explanation="Evidence is complete for human review.",
            )
        )
        return LLMCallResult(
            output=output,
            model="gemini-test",
            model_version="gemini-test-1",
            latency_ms=5,
            prompt_tokens=10,
            output_tokens=10,
        )

    monkeypatch.setattr(
        "app.agents.workflow.structured_reasoning_with_metadata",
        fake_reasoning,
    )
    graph = build_workflow(InMemorySaver())
    config = workflow_config("tenant:supplier:case:run")

    first = await graph.ainvoke(_state(), config)
    assert first["current_stage"] == "evidence_critique_complete"
    assert first["__interrupt__"][0].value["kind"] == "APPROVAL"

    second = await graph.ainvoke(
        Command(
            resume={
                "decision": "APPROVED",
                "task_id": "task-1",
                "evidence_hash": first["evidence_hash"],
                "expected_version": 4,
                "actor_id": "approver-1",
            }
        ),
        config,
    )
    assert second["__interrupt__"][0].value["kind"] == "ERP_CONFIRMATION"
    assert second["human_response"]["decision"] == "APPROVED"

    final = await graph.ainvoke(
        Command(
            resume={
                "status": "SUCCEEDED",
                "operation_id": "operation-1",
                "provider_reference": "ERP-001",
            }
        ),
        config,
    )
    assert final["outcome"] == "COMPLETED"
    assert final["erp_confirmation"]["provider_reference"] == "ERP-001"


@pytest.mark.asyncio
async def test_llm_failure_finishes_blocked_without_human_interrupt(
    monkeypatch,
):
    from app.llm_gateway import LLMProviderError

    async def fail_reasoning(_prompt, _payload, _model):
        raise LLMProviderError(
            "LLM_QUOTA_EXCEEDED",
            retryable=True,
            upgrade_required=True,
        )

    monkeypatch.setattr(
        "app.agents.workflow.structured_reasoning_with_metadata",
        fail_reasoning,
    )
    graph = build_workflow(InMemorySaver())
    result = await graph.ainvoke(
        _state(),
        workflow_config("tenant:supplier:case:blocked"),
    )
    assert result["outcome"] == "BLOCKED"
    assert result["blocker"] == {
        "error_code": "LLM_QUOTA_EXCEEDED",
        "retryable": True,
        "upgrade_required": True,
    }
    assert "__interrupt__" not in result


@pytest.mark.asyncio
async def test_required_control_reviews_precede_final_approval(monkeypatch):
    async def fake_reasoning(_prompt, _payload, model):
        output = (
            ContradictionAnalysis(
                explanation="Review deterministic controls.",
            )
            if model is ContradictionAnalysis
            else EvidenceCritique(
                completeness_score=1,
                cited_evidence_ids=["ev-1"],
                explanation="Ready for controlled review.",
            )
        )
        return LLMCallResult(
            output=output,
            model="gemini-test",
            model_version="gemini-test-1",
            latency_ms=1,
            prompt_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(
        "app.agents.workflow.structured_reasoning_with_metadata",
        fake_reasoning,
    )
    initial = _state()
    initial["required_reviews"] = [
        "DUPLICATE_REVIEW",
        "SANCTIONS_REVIEW",
    ]
    graph = build_workflow(InMemorySaver())
    config = workflow_config("tenant:supplier:case:dual-control")
    first = await graph.ainvoke(initial, config)
    assert first["__interrupt__"][0].value == {
        "kind": "CONTROL_REVIEW",
        "review_type": "DUPLICATE_REVIEW",
        "case_id": initial["case_id"],
        "run_id": initial["run_id"],
        "case_version": 4,
        "evidence_hash": initial["evidence_hash"],
    }

    second = await graph.ainvoke(
        Command(
            resume={
                "decision": "APPROVED",
                "task_id": "duplicate-task",
                "evidence_hash": initial["evidence_hash"],
                "expected_version": 4,
                "actor_id": "procurement-reviewer",
            }
        ),
        config,
    )
    assert second["__interrupt__"][0].value["review_type"] == (
        "SANCTIONS_REVIEW"
    )

    third = await graph.ainvoke(
        Command(
            resume={
                "decision": "APPROVED",
                "task_id": "sanctions-task",
                "evidence_hash": initial["evidence_hash"],
                "expected_version": 5,
                "actor_id": "compliance-reviewer",
            }
        ),
        config,
    )
    assert third["__interrupt__"][0].value["kind"] == "APPROVAL"
    assert third["completed_reviews"] == [
        "DUPLICATE_REVIEW",
        "SANCTIONS_REVIEW",
    ]


def test_sensitive_model_payload_is_rejected_before_provider_call():
    with pytest.raises(ValueError, match="LLM_PAYLOAD_REJECTED"):
        validate_minimized_payload(
            {
                "_data_classification": "SYNTHETIC",
                "evidence": [{"bank_account": "123456"}],
            }
        )
