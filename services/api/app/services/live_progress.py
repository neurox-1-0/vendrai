import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)
LIVE_STEP_NAMESPACE = uuid.UUID("7ce0aeb8-dd2a-4204-9207-5fb3dc448c1a")
LIVE_STEP_STATUSES = {
    "BLOCKED",
    "CANCELLED",
    "FAILED",
    "QUEUED",
    "RETRYING",
    "RUNNING",
    "SUCCESS",
}
LiveProgressCallback = Callable[
    [str, dict[str, Any]],
    Awaitable[None],
]


def _run_key(tenant_id: uuid.UUID, run_id: uuid.UUID) -> str:
    return f"neurox:live-run:{tenant_id}:{run_id}"


def _field(node_name: str, attempt: int) -> str:
    return f"{node_name}:{attempt}"


def _step_id(
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    node_name: str,
    attempt: int,
) -> uuid.UUID:
    return uuid.uuid5(
        LIVE_STEP_NAMESPACE,
        f"{tenant_id}:{run_id}:{node_name}:{attempt}",
    )


async def _client():
    from redis.asyncio import Redis

    return Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=settings.LIVE_PROGRESS_REDIS_TIMEOUT_SECONDS,
        socket_timeout=settings.LIVE_PROGRESS_REDIS_TIMEOUT_SECONDS,
    )


async def publish_live_step(
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    node_name: str,
    attempt: int,
    status: str,
    route_reason: str,
    dependencies: list[str],
    started_at: datetime,
    completed_at: datetime | None,
    latency_ms: int | None,
    error: dict[str, Any],
    redis_client=None,
) -> None:
    """Publish a PII-free, expiring projection without affecting execution."""
    if not settings.LIVE_PROGRESS_ENABLED:
        return
    if status not in LIVE_STEP_STATUSES:
        raise ValueError("LIVE_PROGRESS_STATUS_INVALID")
    payload = {
        "step_id": str(
            _step_id(tenant_id, run_id, node_name, attempt)
        ),
        "tenant_id": str(tenant_id),
        "run_id": str(run_id),
        "node_name": node_name,
        "attempt": attempt,
        "status": status,
        "route_reason": route_reason,
        "dependencies": dependencies,
        "started_at": started_at.astimezone(UTC).isoformat(),
        "completed_at": (
            completed_at.astimezone(UTC).isoformat()
            if completed_at
            else None
        ),
        "latency_ms": latency_ms,
        "error": error,
        "projected_at": datetime.now(UTC).isoformat(),
    }
    owned_client = redis_client is None
    client = redis_client or await _client()
    try:
        key = _run_key(tenant_id, run_id)
        async with client.pipeline(transaction=True) as pipeline:
            pipeline.hset(
                key,
                _field(node_name, attempt),
                json.dumps(payload, separators=(",", ":")),
            )
            pipeline.expire(key, settings.LIVE_PROGRESS_TTL_SECONDS)
            await pipeline.execute()
    finally:
        if owned_client:
            await client.aclose()


def specialist_progress_callback(
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    attempt: int,
    route_reasons: dict[str, str],
    dependencies: dict[str, list[str]],
) -> LiveProgressCallback:
    async def report(
        node_name: str,
        progress: dict[str, Any],
    ) -> None:
        await publish_live_step(
            tenant_id=tenant_id,
            run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            status=str(progress["status"]),
            route_reason=route_reasons.get(
                node_name,
                "Mandatory safety investigation retained after planner failure.",
            ),
            dependencies=dependencies.get(node_name, []),
            started_at=progress["started_at"],
            completed_at=progress.get("completed_at"),
            latency_ms=progress.get("latency_ms"),
            error=progress.get("error", {}),
        )

    return report


async def read_live_steps(
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    redis_client=None,
) -> list[dict[str, Any]]:
    """Read only the requested tenant/run projection; failure returns no data."""
    if (
        not settings.LIVE_PROGRESS_ENABLED
        or settings.APP_ENV == "test"
        and redis_client is None
    ):
        return []
    owned_client = redis_client is None
    try:
        client = redis_client or await _client()
        raw_items = await client.hgetall(_run_key(tenant_id, run_id))
        items: list[dict[str, Any]] = []
        for raw in raw_items.values():
            try:
                item = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if (
                item.get("tenant_id") != str(tenant_id)
                or item.get("run_id") != str(run_id)
                or item.get("status") not in LIVE_STEP_STATUSES
            ):
                continue
            items.append(item)
        return items
    except Exception:
        logger.warning(
            "Live progress read failed for run %s",
            run_id,
            exc_info=True,
        )
        return []
    finally:
        if owned_client and "client" in locals():
            await client.aclose()
