"""Guards for the Redis capability check (plans/90-defect-register.md D-008).

A Redis older than 7.0 answers PING happily and then rejects the rate limiter's
``EXPIRE ... NX``. Before this check existed, that surfaced as a 503 claiming
Redis was unavailable, which sent debugging in entirely the wrong direction.
"""

import pytest
from app.services.redis_support import (
    MINIMUM_REDIS_VERSION,
    parse_redis_version,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7.4.2", (7, 4, 2)),
        ("8.8.1", (8, 8, 1)),
        ("7.0.0", (7, 0, 0)),
        ("6.2.14", (6, 2, 14)),
        ("3.0.504", (3, 0, 504)),
        # Pre-release suffixes must not break comparison.
        ("7.4.0-rc1", (7, 4, 0)),
        ("", ()),
        ("garbage", ()),
    ],
)
def test_parse_redis_version(raw: str, expected: tuple[int, ...]) -> None:
    assert parse_redis_version(raw) == expected


@pytest.mark.parametrize("raw", ["7.0.0", "7.4.2", "8.8.1"])
def test_supported_versions_meet_the_minimum(raw: str) -> None:
    assert parse_redis_version(raw) >= MINIMUM_REDIS_VERSION


@pytest.mark.parametrize("raw", ["6.2.14", "5.0.14", "3.0.504"])
def test_versions_below_seven_are_rejected(raw: str) -> None:
    """These are the versions that would fail on EXPIRE ... NX at runtime."""
    assert parse_redis_version(raw) < MINIMUM_REDIS_VERSION


def test_minimum_is_seven_zero() -> None:
    """EXPIRE ... NX was introduced in Redis 7.0; the floor tracks that."""
    assert MINIMUM_REDIS_VERSION == (7, 0)
