import os
import uuid

import psycopg
import pytest
from psycopg import AsyncConnection

REQUIRED_URLS = (
    "NEUROX_LIVE_MIGRATION_URL",
    "NEUROX_LIVE_APP_URL",
    "NEUROX_LIVE_WORKER_URL",
    "NEUROX_LIVE_RELAY_URL",
    "NEUROX_LIVE_AUDIT_URL",
)
pytestmark = pytest.mark.skipif(
    any(not os.getenv(name) for name in REQUIRED_URLS),
    reason="requires opt-in URLs for every live PostgreSQL role",
)


async def _connect(url: str, tenant_id: uuid.UUID | None = None):
    connection = await AsyncConnection.connect(url, autocommit=True)
    if tenant_id:
        await connection.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            (str(tenant_id),),
        )
    return connection


@pytest.mark.asyncio
async def test_api_worker_audit_and_relay_roles_are_least_privilege_and_scoped():
    suffix = uuid.uuid4().hex[:12]
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    case_a = uuid.uuid4()
    case_b = uuid.uuid4()
    outbox_a = uuid.uuid4()
    outbox_b = uuid.uuid4()

    migration = await _connect(os.environ["NEUROX_LIVE_MIGRATION_URL"])
    try:
        for tenant_id, user_id, case_id, event_id, label in (
            (tenant_a, user_a, case_a, outbox_a, "a"),
            (tenant_b, user_b, case_b, outbox_b, "b"),
        ):
            await migration.execute(
                """INSERT INTO tenants (tenant_id, name, slug, status)
                   VALUES (%s, %s, %s, 'ACTIVE')""",
                (tenant_id, f"Test tenant {label}", f"rls-{suffix}-{label}"),
            )
            await migration.execute(
                """INSERT INTO users
                   (user_id, tenant_id, external_subject, email, full_name,
                    roles, status)
                   VALUES (%s, %s, %s, %s, %s, '[]'::jsonb, 'ACTIVE')""",
                (
                    user_id,
                    tenant_id,
                    f"subject-{suffix}-{label}",
                    f"{suffix}-{label}@example.invalid",
                    f"Test User {label}",
                ),
            )
            await migration.execute(
                """INSERT INTO cases
                   (case_id, tenant_id, case_number, case_type, status,
                    requester_user_id, title, priority, current_version)
                   VALUES (%s, %s, %s, 'VENDOR_ONBOARDING', 'DRAFT',
                           %s, %s, 'NORMAL', 1)""",
                (
                    case_id,
                    tenant_id,
                    f"RLS-{suffix}-{label}",
                    user_id,
                    f"RLS case {label}",
                ),
            )
            await migration.execute(
                """INSERT INTO outbox_events
                   (event_id, tenant_id, aggregate_type, aggregate_id,
                    aggregate_version, event_type, schema_version,
                    idempotency_key, correlation_id, payload, attempts)
                   VALUES (%s, %s, 'case', %s, 1, 'test.rls.v1', 1,
                           %s, %s, '{}'::jsonb, 0)""",
                (
                    event_id,
                    tenant_id,
                    case_id,
                    f"rls:{suffix}:{label}",
                    uuid.uuid4(),
                ),
            )
    finally:
        await migration.close()

    for role_url in (
        os.environ["NEUROX_LIVE_APP_URL"],
        os.environ["NEUROX_LIVE_WORKER_URL"],
    ):
        connection = await _connect(role_url, tenant_a)
        try:
            rows = await connection.execute("SELECT tenant_id FROM cases")
            assert [row[0] for row in await rows.fetchall()] == [tenant_a]
        finally:
            await connection.close()

    audit = await _connect(os.environ["NEUROX_LIVE_AUDIT_URL"], tenant_b)
    try:
        rows = await audit.execute("SELECT tenant_id FROM cases")
        assert [row[0] for row in await rows.fetchall()] == [tenant_b]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await audit.execute(
                "UPDATE cases SET title = 'forbidden' WHERE case_id = %s",
                (case_b,),
            )
    finally:
        await audit.close()

    relay = await _connect(os.environ["NEUROX_LIVE_RELAY_URL"])
    try:
        rows = await relay.execute(
            "SELECT tenant_id FROM outbox_events WHERE event_id IN (%s, %s)",
            (outbox_a, outbox_b),
        )
        assert {row[0] for row in await rows.fetchall()} == {tenant_a, tenant_b}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await relay.execute("SELECT tenant_id FROM cases LIMIT 1")
    finally:
        await relay.close()
