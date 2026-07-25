import asyncio
from datetime import UTC, datetime

from app.models import OutboxEvent
from app.observability import configure_worker_observability
from app.workers.common import declare_topology, message_for, open_broker
from app.workers.database import WorkerSession
from sqlalchemy import select

REQUIRED_ROUTED_EVENTS = {
    "agent.analysis.requested.v1",
    "agent.erp.confirmed.v1",
    "approval.approved.v1",
    "approval.escalated.v1",
    "approval.more_info.v1",
    "approval.rejected.v1",
    "case.submitted.v1",
    "clarification.answered.v1",
    "document.processing.requested.v1",
    "erp.sync.requested.v1",
    "invoice.analysis.requested.v1",
    "invoice.resolution.approved.v1",
    "invoice.submitted.v1",
    "notification.delivery.requested.v1",
    "policy.published.v1",
    "review.resolved.v1",
    "sanctions.import.requested.v1",
}


async def relay_batch(limit: int = 100) -> int:
    connection = await open_broker()
    try:
        channel = await connection.channel(publisher_confirms=True)
        exchange, _ = await declare_topology(channel)
        async with WorkerSession() as session:
            async with session.begin():
                events = (await session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None), OutboxEvent.available_at <= datetime.now(UTC))
                    .order_by(OutboxEvent.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )).scalars().all()
                for event in events:
                    envelope = {
                        "specversion": "1.0", "event_id": str(event.event_id), "event_type": event.event_type,
                        "schema_version": event.schema_version, "occurred_at": event.created_at.isoformat(),
                        "tenant_id": str(event.tenant_id), "aggregate_type": event.aggregate_type,
                        "aggregate_id": str(event.aggregate_id), "aggregate_version": event.aggregate_version,
                        "correlation_id": str(event.correlation_id),
                        "causation_id": str(event.causation_id) if event.causation_id else None,
                        "traceparent": event.traceparent, "payload": event.payload,
                    }
                    try:
                        await exchange.publish(
                            message_for(envelope),
                            routing_key=event.event_type,
                            mandatory=event.event_type
                            in REQUIRED_ROUTED_EVENTS,
                        )
                        event.published_at = datetime.now(UTC)
                        event.last_error = None
                    except Exception as exc:
                        event.attempts += 1
                        event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                        raise
                return len(events)
    finally:
        await connection.close()


async def main() -> None:
    configure_worker_observability("outbox-relay")
    while True:
        count = await relay_batch()
        await asyncio.sleep(0.1 if count else 1.0)


if __name__ == "__main__":
    asyncio.run(main())
