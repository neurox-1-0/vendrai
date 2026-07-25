from app.workers.outbox import REQUIRED_ROUTED_EVENTS


def test_every_safety_critical_command_requires_a_bound_consumer():
    expected = {
        "document.processing.requested.v1",
        "case.submitted.v1",
        "agent.analysis.requested.v1",
        "invoice.submitted.v1",
        "invoice.analysis.requested.v1",
        "approval.approved.v1",
        "approval.rejected.v1",
        "approval.more_info.v1",
        "approval.escalated.v1",
        "review.resolved.v1",
        "clarification.answered.v1",
        "erp.sync.requested.v1",
        "invoice.resolution.approved.v1",
        "agent.erp.confirmed.v1",
        "notification.delivery.requested.v1",
        "policy.published.v1",
        "sanctions.import.requested.v1",
    }
    assert REQUIRED_ROUTED_EVENTS == expected


def test_fact_events_do_not_block_the_outbox_when_no_adapter_is_installed():
    facts = {
        "case.created.v1",
        "case.claimed.v1",
        "case.released.v1",
        "audit.export.created.v1",
        "sanctions.import.completed.v1",
        "sanctions.import.failed.v1",
    }
    assert facts.isdisjoint(REQUIRED_ROUTED_EVENTS)
