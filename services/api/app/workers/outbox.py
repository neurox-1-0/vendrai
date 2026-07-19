import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import OutboxEvent
from app.workers.common import declare_topology, message_for, open_broker
from app.workers.database import WorkerSession


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
                        await exchange.publish(message_for(envelope), routing_key=event.event_type, mandatory=True)
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
    while True:
        count = await relay_batch()
        await asyncio.sleep(0.1 if count else 1.0)


if __name__ == "__main__":
    asyncio.run(main())
