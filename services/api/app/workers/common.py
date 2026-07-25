import json
import logging
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType, IncomingMessage, Message

from app.config import settings


logger = logging.getLogger(__name__)
Handler = Callable[[dict[str, Any]], Awaitable[None]]


async def open_broker():
    return await aio_pika.connect_robust(
        settings.RABBITMQ_URL,
        timeout=10,
        fail_fast=True,
        reconnect_interval=5,
        on_return_raises=True,
        client_properties={"connection_name": "neurox-worker"},
    )


async def declare_topology(channel: aio_pika.abc.AbstractChannel):
    events = await channel.declare_exchange("neurox.events", ExchangeType.TOPIC, durable=True)
    dead = await channel.declare_exchange("neurox.dead", ExchangeType.TOPIC, durable=True)
    return events, dead


async def consume(worker_name: str, bindings: list[str], handler: Handler) -> None:
    connection = await open_broker()
    channel = await connection.channel(publisher_confirms=True)
    await channel.set_qos(prefetch_count=1)
    events, dead = await declare_topology(channel)
    queue = await channel.declare_queue(
        f"neurox.{worker_name}", durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": "neurox.dead",
            "x-dead-letter-routing-key": worker_name,
        },
    )
    dead_queue = await channel.declare_queue(f"neurox.{worker_name}.dead", durable=True, arguments={"x-queue-type": "quorum"})
    await dead_queue.bind(dead, routing_key=worker_name)
    retry = await channel.declare_exchange("neurox.retry", ExchangeType.TOPIC, durable=True)
    retry_delays_ms = (1_000, 5_000, 30_000, 120_000)
    for binding in bindings:
        await queue.bind(events, routing_key=binding)
        for attempt, delay_ms in enumerate(retry_delays_ms, start=1):
            retry_routing_key = f"{worker_name}.{binding}.{attempt}"
            retry_queue = await channel.declare_queue(
                f"neurox.{worker_name}.retry.{binding}.{attempt}",
                durable=True,
                arguments={
                    "x-queue-type": "quorum",
                    "x-message-ttl": delay_ms,
                    "x-dead-letter-exchange": "neurox.events",
                    "x-dead-letter-routing-key": binding,
                },
            )
            await retry_queue.bind(retry, routing_key=retry_routing_key)

    async def callback(message: IncomingMessage) -> None:
        envelope: dict[str, Any] | None = None
        try:
            envelope = json.loads(message.body)
            if not isinstance(envelope, dict):
                raise ValueError("EVENT_ENVELOPE_MUST_BE_AN_OBJECT")
            await handler(envelope)
            await message.ack()
        except Exception:
            headers = dict(message.headers or {})
            retry_attempt = int(headers.get("x-retry-attempt", 0)) + 1
            logger.exception("%s failed event %s", worker_name, message.message_id)
            if envelope is None:
                await message.reject(requeue=False)
                return
            if retry_attempt > len(retry_delays_ms):
                await message.reject(requeue=False)
            else:
                headers["x-retry-attempt"] = retry_attempt
                event_type = envelope.get("event_type")
                if event_type not in bindings:
                    await message.reject(requeue=False)
                    return
                retry_message = Message(
                    body=message.body,
                    content_type=message.content_type,
                    message_id=message.message_id,
                    correlation_id=message.correlation_id,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers=headers,
                )
                await retry.publish(
                    retry_message,
                    routing_key=f"{worker_name}.{event_type}.{retry_attempt}",
                    mandatory=True,
                )
                await message.ack()

    await queue.consume(callback, no_ack=False)
    logger.info("%s consuming %s", worker_name, bindings)
    await asyncio.Future()


def message_for(envelope: dict[str, Any]) -> Message:
    return Message(
        body=json.dumps(envelope, separators=(",", ":"), default=str).encode(),
        content_type="application/cloudevents+json",
        message_id=envelope["event_id"],
        correlation_id=envelope.get("correlation_id"),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        headers={"schema_version": envelope.get("schema_version", 1), "tenant_id": envelope["tenant_id"]},
    )
