import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.llm_gateway import LLMProviderError

MAX_PARALLEL_SPECIALISTS = 12
ProgressCallback = Callable[
    [str, dict[str, Any]],
    Awaitable[None],
]
logger = logging.getLogger(__name__)


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


async def _notify(
    callback: ProgressCallback | None,
    operation_name: str,
    progress: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        await callback(operation_name, progress)
    except asyncio.CancelledError:
        raise
    except Exception:
        # A projection is observability, not workflow authority. Redis or
        # callback failure must not cancel safety checks or erase siblings.
        logger.warning(
            "Specialist progress projection failed for %s",
            operation_name,
            exc_info=True,
        )


async def _capture(
    operation_name: str,
    awaitable: Awaitable[Any],
    on_progress: ProgressCallback | None,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    await _notify(
        on_progress,
        operation_name,
        {
            "status": "RUNNING",
            "started_at": started_at,
            "completed_at": None,
            "latency_ms": None,
            "error": {},
        },
    )
    try:
        result = await awaitable
        captured = {
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
        captured = {
            "status": "FAILED",
            "result": None,
            "error": _failure(exc),
            "started_at": started_at,
            "completed_at": datetime.now(UTC),
            "latency_ms": round(
                (time.perf_counter() - started) * 1000
            ),
        }
    await _notify(
        on_progress,
        operation_name,
        {
            key: value
            for key, value in captured.items()
            if key != "result"
        },
    )
    return captured


async def execute_parallel(
    operations: dict[str, Awaitable[Any]],
    *,
    on_progress: ProgressCallback | None = None,
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
        *(
            _capture(name, operation, on_progress)
            for name, operation in operations.items()
        )
    )
    return dict(zip(operations, results, strict=True))
