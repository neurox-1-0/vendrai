"""The capability registry is a contract, not documentation.

A capability that is registered but that no worker executes is worse than a
missing one: the planner can select it, it is persisted, and it renders in the
execution map the operator reads - so the operator, the audit trail, and any
reviewer are all told a check happened when nothing ran.

Supplier ``bank_consistency`` was in exactly that state (D-001). These tests
make the whole defect class structurally impossible to reintroduce.

See plans/91-decisions.md ADR-002.
"""

import pytest
from app.agents.planning import CAPABILITIES
from app.workers.agent import SUPPLIER_EXECUTORS
from app.workers.invoice_agent import INVOICE_EXECUTORS

EXECUTORS = {
    "supplier": SUPPLIER_EXECUTORS,
    "invoice": INVOICE_EXECUTORS,
}


def registered(workflow_kind: str) -> set[str]:
    return {
        spec.capability_id
        for spec in CAPABILITIES
        if spec.workflow_kind == workflow_kind
    }


@pytest.mark.parametrize("workflow_kind", sorted(EXECUTORS))
def test_every_registered_capability_has_an_executor(workflow_kind: str):
    missing = registered(workflow_kind) - EXECUTORS[workflow_kind]
    assert not missing, (
        f"{workflow_kind} capabilities are registered but no worker executes "
        f"them: {sorted(missing)}. Implement the operation, or remove the spec "
        "from the registry - advertising an unexecuted check is a correctness "
        "failure, not a gap."
    )


@pytest.mark.parametrize("workflow_kind", sorted(EXECUTORS))
def test_no_executor_claims_an_unregistered_capability(workflow_kind: str):
    extra = EXECUTORS[workflow_kind] - registered(workflow_kind)
    assert not extra, (
        f"{workflow_kind} worker claims to execute capabilities that are not "
        f"registered: {sorted(extra)}. The planner can never select them, so "
        "the executor branch is dead code."
    )


def test_every_workflow_kind_in_the_registry_has_an_executor_set():
    """A new workflow must not be able to slip in without this check."""
    kinds = {spec.workflow_kind for spec in CAPABILITIES}
    assert kinds == set(EXECUTORS), (
        "A workflow kind exists in the registry with no declared executor set, "
        "so nothing verifies its capabilities are executable."
    )


def test_the_check_fails_when_a_capability_loses_its_executor():
    """Prove the assertion above actually bites."""
    weakened = SUPPLIER_EXECUTORS - {"bank_consistency"}
    assert registered("supplier") - weakened == {"bank_consistency"}
