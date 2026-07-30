"""Redis capability checks.

The rate limiter uses ``EXPIRE ... NX``, which Redis only added in 7.0. Older
servers answer ``PING`` perfectly well and then reject that one command, so a
naive "is Redis up?" check reports success while every rate-limited request
fails. Detecting the version at startup turns a confusing runtime 503 into one
clear message. See plans/90-defect-register.md D-008.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# EXPIRE ... NX was introduced in Redis 7.0.
MINIMUM_REDIS_VERSION: tuple[int, int] = (7, 0)


class RedisVersionUnsupported(RuntimeError):
    """Raised when the configured Redis cannot serve the commands we rely on."""


def parse_redis_version(raw: str) -> tuple[int, ...]:
    """Parse ``redis_version`` into a comparable tuple.

    Trailing non-numeric segments are ignored so pre-release builds such as
    ``7.4.0-rc1`` compare as ``(7, 4, 0)``.
    """
    parts: list[int] = []
    for segment in raw.split("."):
        digits = ""
        for character in segment:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


async def verify_redis_version() -> str | None:
    """Check the Redis server version against the minimum this service needs.

    Returns the detected version, or ``None`` when the check was skipped.
    Raises :class:`RedisVersionUnsupported` when the server is too old.
    A server that is merely unreachable is logged and tolerated: readiness
    probes cover availability, and refusing to boot on a transient outage would
    make startup ordering brittle.
    """
    if not settings.RATE_LIMIT_ENABLED or settings.APP_ENV == "test":
        return None

    from redis.asyncio import Redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import ResponseError as RedisResponseError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    minimum = ".".join(str(part) for part in MINIMUM_REDIS_VERSION)
    client = Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        info = await client.info("server")
    except (RedisConnectionError, RedisTimeoutError) as exc:
        # Unreachable is not our problem here - readiness probes cover it, and
        # refusing to boot during a transient outage makes startup brittle.
        logger.warning(
            "redis_version_check_skipped: could not reach Redis (%s). "
            "Readiness checks will report availability.",
            type(exc).__name__,
        )
        return None
    except RedisResponseError as exc:
        # The server answered and rejected the request. Modern redis-py opens
        # every connection with HELLO (Redis 6.0+), so a rejection here means
        # the server predates that - comfortably below our 7.0 floor.
        raise RedisVersionUnsupported(
            f"REDIS_VERSION_UNSUPPORTED: the server rejected the client "
            f"handshake ({exc}), which means it is older than Redis 6.0. "
            f"This service requires >= {minimum} because the rate limiter uses "
            "'EXPIRE ... NX'. Update Redis, or set RATE_LIMIT_ENABLED=false "
            "for local development."
        ) from exc
    finally:
        await client.aclose()

    raw_version = str(info.get("redis_version", ""))
    parsed = parse_redis_version(raw_version)
    if not parsed:
        logger.warning(
            "redis_version_check_skipped: server reported an unparseable "
            "version %r.",
            raw_version,
        )
        return None

    if parsed < MINIMUM_REDIS_VERSION:
        raise RedisVersionUnsupported(
            f"REDIS_VERSION_UNSUPPORTED: found {raw_version}, requires >= {minimum}. "
            "The rate limiter uses 'EXPIRE ... NX', which older servers reject. "
            "Update Redis, or set RATE_LIMIT_ENABLED=false for local development."
        )
    return raw_version
