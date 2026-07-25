import pytest
from app.agents.planning import (
    InvestigationPlan,
    PlannedCapability,
    create_investigation_plan,
    validate_plan,
)
from app.llm_gateway import LLMCallResult, LLMProviderError


def _supplier_plan(*capabilities: str) -> InvestigationPlan:
    return InvestigationPlan(
        objective="Investigate a synthetic supplier.",
        strategy_summary="Collect independent evidence before reasoning.",
        selected_capabilities=[
            PlannedCapability(
                capability_id=capability,
                rationale="The observable facts make this capability eligible.",
                priority=index + 1,
            )
            for index, capability in enumerate(capabilities)
        ],
        stop_conditions=["Mandatory evidence is unavailable."],
    )


def test_plan_validation_builds_parallel_supplier_group():
    groups, eligible = validate_plan(
        "supplier",
        {
            "documents_ready": True,
            "legal_name_available": True,
            "bank_account_available": False,
            "registered_country_available": False,
        },
        _supplier_plan(
            "document_intelligence",
            "duplicate_detection",
            "sanctions_screening",
            "policy_retrieval",
        ),
    )
    assert groups == [
        ["document_intelligence", "policy_retrieval"],
        ["duplicate_detection", "sanctions_screening"],
    ]
    assert "bank_consistency" not in eligible


def test_plan_validation_rejects_missing_mandatory_capability():
    with pytest.raises(LLMProviderError, match="LLM_OUTPUT_INVALID"):
        validate_plan(
            "supplier",
            {
                "documents_ready": True,
                "legal_name_available": True,
            },
            _supplier_plan(
                "document_intelligence",
                "duplicate_detection",
                "policy_retrieval",
            ),
        )


@pytest.mark.asyncio
async def test_planner_calls_real_gateway_contract_and_returns_metadata(
    monkeypatch,
):
    async def fake_call(_prompt, payload, model):
        assert payload["_data_classification"] == "SYNTHETIC"
        assert all(
            isinstance(value, bool)
            for value in payload["observable_facts"].values()
        )
        output = _supplier_plan(
            "document_intelligence",
            "duplicate_detection",
            "sanctions_screening",
            "policy_retrieval",
        )
        assert model is InvestigationPlan
        return LLMCallResult(
            output=output,
            model="gemini-test",
            model_version="gemini-test-1",
            latency_ms=37,
            prompt_tokens=20,
            output_tokens=15,
        )

    monkeypatch.setattr("app.agents.planning.call_llm", fake_call)
    plan = await create_investigation_plan(
        "supplier",
        "Investigate a synthetic supplier.",
        {
            "documents_ready": True,
            "legal_name_available": True,
        },
    )
    assert plan.latency_ms == 37
    assert plan.model_version == "gemini-test-1"
    assert plan.execution_groups[1] == [
        "duplicate_detection",
        "sanctions_screening",
    ]
