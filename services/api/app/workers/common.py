import asyncio
import json
import logging
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
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    events, dead = await declare_topology(channel)
    queue = await channel.declare_queue(
        f"neurox.{worker_name}", durable=True,
        arguments={"x-queue-type": "quorum", "x-dead-letter-exchange": "neurox.dead"},
    )
    dead_queue = await channel.declare_queue(f"neurox.{worker_name}.dead", durable=True, arguments={"x-queue-type": "quorum"})
    await dead_queue.bind(dead, routing_key="#")
    for binding in bindings:
        await queue.bind(events, routing_key=binding)

    async def callback(message: IncomingMessage) -> None:
        try:
            envelope = json.loads(message.body)
            await handler(envelope)
            await message.ack()
        except Exception:
            delivery_count = int(message.headers.get("x-delivery-count", 0)) if message.headers else 0
            logger.exception("%s failed event %s", worker_name, message.message_id)
            if delivery_count >= 4:
                await message.reject(requeue=False)
            else:
                await asyncio.sleep(min(2 ** delivery_count, 30))
                await message.nack(requeue=True)

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
