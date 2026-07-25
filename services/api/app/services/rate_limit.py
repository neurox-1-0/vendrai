import hashlib

from app.auth import CurrentPrincipal
from app.config import settings
from fastapi import HTTPException, Request


async def enforce_rate_limit(request: Request, principal: CurrentPrincipal) -> None:
    if not settings.RATE_LIMIT_ENABLED or settings.APP_ENV == "test":
        return
    from redis.asyncio import Redis

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
    except Exception as exc:
        raise HTTPException(
            503,
            detail={"code": "RATE_LIMIT_SERVICE_UNAVAILABLE"},
        ) from exc
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
