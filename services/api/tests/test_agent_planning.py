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


# Every supplier capability that is mandatory once documents are ready and a
# legal name is available. Kept as a constant so a new mandatory capability
# fails one obvious assertion rather than every test in this file.
MANDATORY_SUPPLIER_CAPABILITIES = (
    "document_intelligence",
    "duplicate_detection",
    "sanctions_screening",
    "policy_retrieval",
    "document_completeness",
    "supplier_controls",
    "injection_scan",
    "risk_screening",
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
        _supplier_plan(*MANDATORY_SUPPLIER_CAPABILITIES),
    )
    # Capabilities with no unmet dependency run together; the rest wait for
    # document_intelligence.
    assert groups[0] == [
        "document_intelligence",
        "policy_retrieval",
        "injection_scan",
    ]
    assert set(groups[1]) == {
        "duplicate_detection",
        "sanctions_screening",
        "document_completeness",
        "supplier_controls",
        "risk_screening",
    }
    # bank_consistency needs bank and country evidence, neither of which this
    # case has, so it must not be offered to the planner at all.
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
        output = _supplier_plan(*MANDATORY_SUPPLIER_CAPABILITIES)
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
    assert {"duplicate_detection", "sanctions_screening"}.issubset(
        plan.execution_groups[1]
    )
