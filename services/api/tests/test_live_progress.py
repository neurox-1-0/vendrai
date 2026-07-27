import json
import uuid
from datetime import UTC, datetime

import pytest
from app.services.live_progress import (
    publish_live_step,
    read_live_steps,
)


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def hset(self, key, field, value):
        self.commands.append(("hset", key, field, value))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for command in self.commands:
            if command[0] == "hset":
                _, key, field, value = command
                self.client.hashes.setdefault(key, {})[field] = value
                results.append(1)
            else:
                _, key, ttl = command
                self.client.expiries[key] = ttl
                results.append(True)
        return results


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.expiries = {}

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)

    async def hgetall(self, key):
        return self.hashes.get(key, {})


@pytest.mark.asyncio
async def test_live_progress_is_tenant_scoped_and_expiring():
    client = FakeRedis()
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    started_at = datetime.now(UTC)

    await publish_live_step(
        tenant_id=tenant_id,
        run_id=run_id,
        node_name="sanctions_screening",
        attempt=2,
        status="RUNNING",
        route_reason="Identity evidence requires screening.",
        dependencies=["document_intelligence"],
        started_at=started_at,
        completed_at=None,
        latency_ms=None,
        error={},
        redis_client=client,
    )

    visible = await read_live_steps(
        tenant_id,
        run_id,
        redis_client=client,
    )
    hidden = await read_live_steps(
        other_tenant_id,
        run_id,
        redis_client=client,
    )

    assert len(visible) == 1
    assert visible[0]["status"] == "RUNNING"
    assert visible[0]["tenant_id"] == str(tenant_id)
    assert hidden == []
    key = f"neurox:live-run:{tenant_id}:{run_id}"
    assert client.expiries[key] == 900


@pytest.mark.asyncio
async def test_live_progress_discards_corrupt_or_mismatched_payloads():
    client = FakeRedis()
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()
    key = f"neurox:live-run:{tenant_id}:{run_id}"
    client.hashes[key] = {
        "corrupt": "{",
        "wrong-tenant": json.dumps(
            {
                "tenant_id": str(uuid.uuid4()),
                "run_id": str(run_id),
                "status": "RUNNING",
            }
        ),
        "invalid-status": json.dumps(
            {
                "tenant_id": str(tenant_id),
                "run_id": str(run_id),
                "status": "UNTRUSTED",
            }
        ),
    }

    assert await read_live_steps(
        tenant_id,
        run_id,
        redis_client=client,
    ) == []
