from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.llm_gateway import LLMCallResult, LLMProviderError
from app.llm_gateway import structured_reasoning_with_metadata as call_llm

WorkflowKind = Literal["supplier", "invoice"]


class CapabilitySpec(BaseModel):
    capability_id: str
    workflow_kind: WorkflowKind
    purpose: str
    prerequisites: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    mandatory_when_eligible: bool = False
    failure_policy: Literal["OPTIONAL", "RETRYABLE", "BLOCKING"]


class PlannedCapability(BaseModel):
    capability_id: str = Field(min_length=3, max_length=80)
    rationale: str = Field(min_length=3, max_length=300)
    priority: int = Field(ge=1, le=10)


class InvestigationPlan(BaseModel):
    objective: str = Field(min_length=3, max_length=400)
    strategy_summary: str = Field(min_length=3, max_length=800)
    selected_capabilities: list[PlannedCapability] = Field(
        min_length=1,
        max_length=12,
    )
    stop_conditions: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_capabilities(self):
        identifiers = [
            item.capability_id for item in self.selected_capabilities
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("DUPLICATE_CAPABILITY")
        return self


@dataclass(frozen=True)
class ValidatedPlan:
    output: InvestigationPlan
    execution_groups: list[list[str]]
    eligible_capabilities: list[str]
    latency_ms: int
    model_version: str
    prompt_tokens: int | None
    output_tokens: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.output.model_dump(mode="json"),
            "execution_groups": self.execution_groups,
            "eligible_capabilities": self.eligible_capabilities,
            "latency_ms": self.latency_ms,
            "model_version": self.model_version,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
        }


CAPABILITIES = (
    CapabilitySpec(
        capability_id="document_intelligence",
        workflow_kind="supplier",
        purpose="Use locally extracted document fields and confidence.",
        prerequisites=["documents_ready"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="duplicate_detection",
        workflow_kind="supplier",
        purpose="Search persistent vendor records for identity collisions.",
        prerequisites=["legal_name_available"],
        dependencies=["document_intelligence"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="sanctions_screening",
        workflow_kind="supplier",
        purpose="Screen identity against current official-list snapshots.",
        prerequisites=["legal_name_available"],
        dependencies=["document_intelligence"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="policy_retrieval",
        workflow_kind="supplier",
        purpose="Retrieve current tenant policy clauses for this case.",
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="bank_consistency",
        workflow_kind="supplier",
        purpose="Investigate available bank and registration-country evidence.",
        prerequisites=[
            "bank_account_available",
            "registered_country_available",
        ],
        dependencies=["document_intelligence"],
        failure_policy="RETRYABLE",
    ),
    CapabilitySpec(
        capability_id="document_intelligence",
        workflow_kind="invoice",
        purpose="Use locally extracted invoice fields and confidence.",
        prerequisites=["documents_ready"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="po_retrieval",
        workflow_kind="invoice",
        purpose="Retrieve the referenced purchase order.",
        prerequisites=["po_reference_available"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="grn_retrieval",
        workflow_kind="invoice",
        purpose="Retrieve accepted goods receipts for the purchase order.",
        prerequisites=["po_reference_available"],
        dependencies=["po_retrieval"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="vendor_resolution",
        workflow_kind="invoice",
        purpose="Resolve the invoice identity against the vendor master.",
        prerequisites=["vendor_identity_available"],
        dependencies=["document_intelligence"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="duplicate_invoice",
        workflow_kind="invoice",
        purpose="Search invoice history for an identity collision.",
        prerequisites=[
            "invoice_number_available",
            "vendor_identity_available",
        ],
        dependencies=["vendor_resolution"],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="policy_retrieval",
        workflow_kind="invoice",
        purpose="Retrieve current tolerance and exception policy clauses.",
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="three_way_match",
        workflow_kind="invoice",
        purpose="Compare invoice, purchase order, and goods receipt evidence.",
        prerequisites=["po_reference_available"],
        dependencies=[
            "document_intelligence",
            "po_retrieval",
            "grn_retrieval",
        ],
        mandatory_when_eligible=True,
        failure_policy="BLOCKING",
    ),
    CapabilitySpec(
        capability_id="bank_consistency",
        workflow_kind="invoice",
        purpose="Compare invoice bank evidence with the resolved vendor.",
        prerequisites=[
            "bank_account_available",
            "vendor_identity_available",
        ],
        dependencies=["document_intelligence", "vendor_resolution"],
        failure_policy="BLOCKING",
    ),
)


def eligible_capabilities(
    workflow_kind: WorkflowKind,
    observable_facts: dict[str, bool],
) -> list[CapabilitySpec]:
    return [
        capability
        for capability in CAPABILITIES
        if capability.workflow_kind == workflow_kind
        and all(
            observable_facts.get(prerequisite, False)
            for prerequisite in capability.prerequisites
        )
    ]


def _execution_groups(
    selected: list[str],
    specs: dict[str, CapabilitySpec],
) -> list[list[str]]:
    remaining = list(selected)
    complete: set[str] = set()
    groups: list[list[str]] = []
    while remaining:
        ready = [
            capability_id
            for capability_id in remaining
            if all(
                dependency in complete or dependency not in selected
                for dependency in specs[capability_id].dependencies
            )
        ]
        if not ready:
            raise LLMProviderError("LLM_OUTPUT_INVALID", retryable=True)
        groups.append(ready)
        complete.update(ready)
        remaining = [
            capability_id
            for capability_id in remaining
            if capability_id not in complete
        ]
    return groups


def validate_plan(
    workflow_kind: WorkflowKind,
    observable_facts: dict[str, bool],
    output: InvestigationPlan,
) -> tuple[list[list[str]], list[str]]:
    eligible = eligible_capabilities(workflow_kind, observable_facts)
    specs = {item.capability_id: item for item in eligible}
    selected = [
        item.capability_id for item in output.selected_capabilities
    ]
    if any(capability_id not in specs for capability_id in selected):
        raise LLMProviderError("LLM_OUTPUT_INVALID", retryable=True)
    mandatory = {
        item.capability_id
        for item in eligible
        if item.mandatory_when_eligible
    }
    if not mandatory.issubset(selected):
        raise LLMProviderError("LLM_OUTPUT_INVALID", retryable=True)
    for capability_id in selected:
        required_dependencies = {
            dependency
            for dependency in specs[capability_id].dependencies
            if dependency in specs
        }
        if not required_dependencies.issubset(selected):
            raise LLMProviderError("LLM_OUTPUT_INVALID", retryable=True)
    return _execution_groups(selected, specs), sorted(specs)


async def create_investigation_plan(
    workflow_kind: WorkflowKind,
    objective: str,
    observable_facts: dict[str, bool],
) -> ValidatedPlan:
    eligible = eligible_capabilities(workflow_kind, observable_facts)
    payload = {
        "_data_classification": settings.LLM_DATA_CLASSIFICATION,
        "workflow_kind": workflow_kind,
        "objective": objective,
        "observable_facts": {
            key: bool(value)
            for key, value in sorted(observable_facts.items())
        },
        "eligible_capabilities": [
            capability.model_dump(mode="json")
            for capability in eligible
        ],
    }
    result: LLMCallResult[InvestigationPlan] = await call_llm(
        (
            "Create a minimal investigation plan using only eligible capability "
            "IDs. Include every capability marked mandatory_when_eligible. "
            "Select an optional capability only when observable facts justify "
            "it. Explain selection in operational terms. Do not decide the "
            "business outcome, invent evidence, or request an unknown tool."
        ),
        payload,
        InvestigationPlan,
    )
    groups, eligible_ids = validate_plan(
        workflow_kind,
        observable_facts,
        result.output,
    )
    return ValidatedPlan(
        output=result.output,
        execution_groups=groups,
        eligible_capabilities=eligible_ids,
        latency_ms=result.latency_ms,
        model_version=result.model_version,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
    )
