import uuid

import pytest
from app.models import Case, Notification, OutboxEvent, Tenant, User
from app.workers.database import WorkerSession
from app.workers.notification import deliver
from sqlalchemy import select


@pytest.mark.asyncio
async def test_smtp_failure_retries_without_mutating_case(monkeypatch):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    notification_id = uuid.uuid4()
    event_id = uuid.uuid4()
    async with WorkerSession() as session:
        async with session.begin():
            session.add(
                Tenant(tenant_id=tenant_id, name="Test", slug=f"test-{tenant_id}")
            )
            session.add(
                User(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    external_subject=f"sub-{user_id}",
                    email="synthetic@example.invalid",
                    full_name="Synthetic User",
                    roles=["approver"],
                    status="ACTIVE",
                )
            )
            session.add(
                Case(
                    case_id=case_id,
                    tenant_id=tenant_id,
                    case_number=f"TEST-{str(case_id)[:8]}",
                    requester_user_id=user_id,
                    title="Notification isolation",
                    status="APPROVAL_PENDING",
                    current_version=7,
                )
            )
            session.add(
                Notification(
                    notification_id=notification_id,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    user_id=user_id,
                    notification_type="APPROVAL_REQUIRED",
                    title="Synthetic approval",
                    body="A synthetic case needs review.",
                    status="QUEUED",
                )
            )

    def unavailable(*_args, **_kwargs):
        raise OSError("synthetic SMTP outage")

    monkeypatch.setattr(
        "app.workers.notification.send_email",
        unavailable,
    )
    await deliver(
        {
            "event_id": str(event_id),
            "tenant_id": str(tenant_id),
            "payload": {
                "notification_id": str(notification_id),
                "user_id": str(user_id),
                "attempt": 1,
            },
        }
    )

    async with WorkerSession() as session:
        case = await session.get(Case, case_id)
        notification = await session.get(Notification, notification_id)
        retry = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == notification_id,
                OutboxEvent.event_type == "notification.delivery.requested.v1",
            )
        )
    assert case.status == "APPROVAL_PENDING"
    assert case.current_version == 7
    assert notification.status == "RETRYING"
    assert retry is not None
    assert retry.payload["attempt"] == 2
