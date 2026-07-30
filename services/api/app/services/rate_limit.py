import hashlib
import logging

from app.auth import CurrentPrincipal
from app.config import settings
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


async def enforce_rate_limit(request: Request, principal: CurrentPrincipal) -> None:
    if not settings.RATE_LIMIT_ENABLED or settings.APP_ENV == "test":
        return
    from redis.asyncio import Redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import ResponseError as RedisResponseError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    route_digest = hashlib.sha256(
        f"{request.method}:{route_path}".encode()
    ).hexdigest()[:16]
    key = (
        f"neurox:rate:{principal.tenant_id}:{principal.user_id}:"
        f"{route_digest}:{settings.RATE_LIMIT_WINDOW_SECONDS}"
    )
    client = Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        async with client.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS, nx=True)
            count, _ = await pipeline.execute()
    except (RedisConnectionError, RedisTimeoutError) as exc:
        # Redis is genuinely unreachable. Fail closed: we cannot prove the
        # caller is within their quota.
        raise HTTPException(
            503,
            detail={"code": "RATE_LIMIT_SERVICE_UNAVAILABLE"},
        ) from exc
    except RedisResponseError as exc:
        # Redis answered and rejected the command. That is a configuration or
        # version problem on our side, not an outage - most commonly a server
        # older than 7.0 refusing 'EXPIRE ... NX'. Blocking every request on a
        # misconfiguration is worse than not rate limiting, and reporting it as
        # an outage sends whoever debugs it in the wrong direction entirely.
        logger.error(
            "rate_limit_command_rejected: Redis rejected the rate-limit "
            "pipeline (%s). Rate limiting is disabled for this request. "
            "Check that the server is >= 7.0 (EXPIRE ... NX). Detail: %s",
            type(exc).__name__,
            exc,
        )
        return
    finally:
        await client.aclose()
    if int(count) > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "retry_after_seconds": settings.RATE_LIMIT_WINDOW_SECONDS,
            },
            headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
        )
