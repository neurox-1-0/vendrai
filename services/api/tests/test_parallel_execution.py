import asyncio
import time

import pytest
from app.agents.execution import execute_parallel


@pytest.mark.asyncio
async def test_parallel_executor_overlaps_independent_specialists():
    async def operation(value: str):
        await asyncio.sleep(0.05)
        return value

    started = time.perf_counter()
    results = await execute_parallel(
        {
            "duplicate": operation("duplicate-result"),
            "sanctions": operation("sanctions-result"),
            "policy": operation("policy-result"),
        }
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.12
    assert {
        result["result"] for result in results.values()
    } == {
        "duplicate-result",
        "sanctions-result",
        "policy-result",
    }
    latest_start = max(
        result["started_at"] for result in results.values()
    )
    earliest_finish = min(
        result["completed_at"] for result in results.values()
    )
    assert latest_start < earliest_finish


@pytest.mark.asyncio
async def test_parallel_executor_preserves_successful_siblings_on_failure():
    async def succeed():
        await asyncio.sleep(0.02)
        return {"evidence": "retained"}

    async def fail():
        await asyncio.sleep(0.005)
        raise RuntimeError("provider response is deliberately hidden")

    results = await execute_parallel(
        {"policy": fail(), "sanctions": succeed()}
    )

    assert results["policy"]["status"] == "FAILED"
    assert results["policy"]["error"] == {
        "error_code": "SPECIALIST_EXECUTION_FAILED",
        "retryable": True,
        "upgrade_required": False,
        "exception_type": "RuntimeError",
    }
    assert results["sanctions"]["status"] == "SUCCESS"
    assert results["sanctions"]["result"] == {
        "evidence": "retained"
    }


@pytest.mark.asyncio
async def test_parallel_executor_reports_running_and_terminal_progress():
    events = []

    async def report(name, progress):
        events.append((name, progress["status"]))

    async def operation():
        await asyncio.sleep(0)
        return "done"

    results = await execute_parallel(
        {"policy": operation()},
        on_progress=report,
    )

    assert results["policy"]["result"] == "done"
    assert events == [
        ("policy", "RUNNING"),
        ("policy", "SUCCESS"),
    ]


@pytest.mark.asyncio
async def test_parallel_executor_ignores_projection_failure():
    async def broken_projection(_name, _progress):
        raise ConnectionError("redis deliberately unavailable")

    async def operation():
        return {"safety_check": "retained"}

    results = await execute_parallel(
        {"sanctions": operation()},
        on_progress=broken_projection,
    )

    assert results["sanctions"]["status"] == "SUCCESS"
    assert results["sanctions"]["result"] == {
        "safety_check": "retained"
    }
