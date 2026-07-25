import asyncio
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from app.llm_gateway import LLMProviderError

MAX_PARALLEL_SPECIALISTS = 12


def _failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, LLMProviderError):
        return {
            "error_code": exc.error_code,
            "retryable": exc.retryable,
            "upgrade_required": exc.upgrade_required,
            "exception_type": type(exc).__name__,
        }
    return {
        "error_code": "SPECIALIST_EXECUTION_FAILED",
        "retryable": True,
        "upgrade_required": False,
        "exception_type": type(exc).__name__,
    }


async def _capture(awaitable: Awaitable[Any]) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    try:
        result = await awaitable
        return {
            "status": "SUCCESS",
            "result": result,
            "error": {},
            "started_at": started_at,
            "completed_at": datetime.now(UTC),
            "latency_ms": round(
                (time.perf_counter() - started) * 1000
            ),
        }
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {
            "status": "FAILED",
            "result": None,
            "error": _failure(exc),
            "started_at": started_at,
            "completed_at": datetime.now(UTC),
            "latency_ms": round(
                (time.perf_counter() - started) * 1000
            ),
        }


async def execute_parallel(
    operations: dict[str, Awaitable[Any]],
) -> dict[str, dict[str, Any]]:
    """Run bounded siblings without allowing one failure to erase the others."""
    if len(operations) > MAX_PARALLEL_SPECIALISTS:
        for operation in operations.values():
            close = getattr(operation, "close", None)
            if callable(close):
                close()
        raise ValueError("SPECIALIST_FANOUT_LIMIT_EXCEEDED")
    if not operations:
        return {}
    results = await asyncio.gather(
        *(_capture(operation) for operation in operations.values())
    )
    return dict(zip(operations, results, strict=True))
