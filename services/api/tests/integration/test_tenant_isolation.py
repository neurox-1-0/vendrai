"""Live cross-tenant isolation, against real PostgreSQL with the real roles.

RLS unit-tested against SQLite has not been tested. SQLite has no row-level
security, so the test proves the query shape and nothing about the isolation.
These run against the actual non-superuser roles created by
infra/postgres/001-roles.sh, with two populated tenants.

``neurox_relay`` gets the most attention on purpose. It is deliberately granted
BYPASSRLS - a legitimate choice for an outbox relay, and the one role where a
bug becomes a cross-tenant leak rather than an error.
"""

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


@pytest.fixture
async def two_tenants():
    """Two tenants, each with a case, an audit entry, and an outbox event."""
    suffix = uuid.uuid4().hex[:12]
    tenants = {
        "a": {"tenant_id": uuid.uuid4()},
        "b": {"tenant_id": uuid.uuid4()},
    }
    migration = await _connect(os.environ["NEUROX_LIVE_MIGRATION_URL"])
    try:
        for label, data in tenants.items():
            tenant_id = data["tenant_id"]
            data["user_id"] = uuid.uuid4()
            data["case_id"] = uuid.uuid4()
            data["audit_id"] = uuid.uuid4()
            data["event_id"] = uuid.uuid4()

            await migration.execute(
                "INSERT INTO tenants (tenant_id, name, slug, status) "
                "VALUES (%s, %s, %s, 'ACTIVE')",
                (tenant_id, f"Isolation {label}", f"iso-{suffix}-{label}"),
            )
            await migration.execute(
                "INSERT INTO users (user_id, tenant_id, external_subject, "
                "email, full_name, roles, status) "
                "VALUES (%s, %s, %s, %s, %s, '[]'::jsonb, 'ACTIVE')",
                (
                    data["user_id"],
                    tenant_id,
                    f"iso-{suffix}-{label}",
                    f"{suffix}-{label}@example.invalid",
                    f"Isolation user {label}",
                ),
            )
            await migration.execute(
                "INSERT INTO cases (case_id, tenant_id, case_number, case_type, "
                "status, requester_user_id, title, priority, current_version) "
                "VALUES (%s, %s, %s, 'VENDOR_ONBOARDING', 'DRAFT', %s, %s, "
                "'NORMAL', 1)",
                (
                    data["case_id"],
                    tenant_id,
                    f"ISO-{suffix}-{label}",
                    data["user_id"],
                    f"Isolation case {label}",
                ),
            )
            await migration.execute(
                "INSERT INTO audit_logs (audit_log_id, tenant_id, case_id, "
                "actor_type, actor_id, action, resource_type, resource_id, "
                "metadata, previous_hash, record_hash) "
                "VALUES (%s, %s, %s, 'SYSTEM', 'test', 'CASE_CREATED', 'CASE', "
                "%s, '{}'::jsonb, NULL, %s)",
                (
                    data["audit_id"],
                    tenant_id,
                    data["case_id"],
                    str(data["case_id"]),
                    uuid.uuid4().hex + uuid.uuid4().hex[:32],
                ),
            )
            await migration.execute(
                "INSERT INTO outbox_events (event_id, tenant_id, aggregate_type, "
                "aggregate_id, aggregate_version, event_type, schema_version, "
                "idempotency_key, correlation_id, payload, attempts) "
                "VALUES (%s, %s, 'case', %s, 1, 'test.iso.v1', 1, %s, %s, "
                "%s::jsonb, 0)",
                (
                    data["event_id"],
                    tenant_id,
                    data["case_id"],
                    f"iso:{suffix}:{label}",
                    uuid.uuid4(),
                    f'{{"case_id": "{data["case_id"]}"}}',
                ),
            )
    finally:
        await migration.close()
    yield tenants


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["NEUROX_LIVE_APP_URL", "NEUROX_LIVE_WORKER_URL"])
async def test_a_tenant_context_sees_only_its_own_cases(two_tenants, role):
    tenant_a = two_tenants["a"]["tenant_id"]
    connection = await _connect(os.environ[role], tenant_a)
    try:
        rows = await connection.execute(
            "SELECT case_id, tenant_id FROM cases WHERE case_id IN (%s, %s)",
            (two_tenants["a"]["case_id"], two_tenants["b"]["case_id"]),
        )
        found = await rows.fetchall()
        assert [row[0] for row in found] == [two_tenants["a"]["case_id"]], (
            "a tenant context returned another tenant's case"
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_no_tenant_context_returns_nothing_rather_than_everything(
    two_tenants,
):
    """The failure mode that matters: an unset context must not mean "all"."""
    connection = await _connect(os.environ["NEUROX_LIVE_APP_URL"])
    try:
        rows = await connection.execute(
            "SELECT case_id FROM cases WHERE case_id IN (%s, %s)",
            (two_tenants["a"]["case_id"], two_tenants["b"]["case_id"]),
        )
        assert await rows.fetchall() == [], (
            "a connection with no tenant context could read every tenant's cases"
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_a_tenant_cannot_write_a_row_belonging_to_another(two_tenants):
    connection = await _connect(
        os.environ["NEUROX_LIVE_APP_URL"], two_tenants["a"]["tenant_id"]
    )
    try:
        result = await connection.execute(
            "UPDATE cases SET title = 'crossed' WHERE case_id = %s",
            (two_tenants["b"]["case_id"],),
        )
        assert result.rowcount == 0, (
            "tenant A updated a case belonging to tenant B"
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_audit_entries_are_tenant_scoped(two_tenants):
    connection = await _connect(
        os.environ["NEUROX_LIVE_AUDIT_URL"], two_tenants["b"]["tenant_id"]
    )
    try:
        rows = await connection.execute(
            "SELECT audit_log_id FROM audit_logs WHERE audit_log_id IN (%s, %s)",
            (two_tenants["a"]["audit_id"], two_tenants["b"]["audit_id"]),
        )
        assert [row[0] for row in await rows.fetchall()] == [
            two_tenants["b"]["audit_id"]
        ]
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        "NEUROX_LIVE_APP_URL",
        "NEUROX_LIVE_WORKER_URL",
        "NEUROX_LIVE_AUDIT_URL",
        "NEUROX_LIVE_RELAY_URL",
    ],
)
async def test_no_role_can_mutate_the_audit_trail(two_tenants, role):
    """An audit trail any role can edit is not an audit trail."""
    connection = await _connect(os.environ[role], two_tenants["a"]["tenant_id"])
    try:
        for statement, parameters in (
            (
                "UPDATE audit_logs SET action = 'REWRITTEN' WHERE audit_log_id = %s",
                (two_tenants["a"]["audit_id"],),
            ),
            (
                "DELETE FROM audit_logs WHERE audit_log_id = %s",
                (two_tenants["a"]["audit_id"],),
            ),
        ):
            try:
                result = await connection.execute(statement, parameters)
            except (
                psycopg.errors.InsufficientPrivilege,
                psycopg.errors.SyntaxErrorOrAccessRuleViolation,
            ):
                continue
            assert result.rowcount == 0, (
                f"{role} modified an audit row: {statement.split()[0]}"
            )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_the_relay_reads_every_tenants_events_by_design(two_tenants):
    """BYPASSRLS is intentional here. The next test is why it is safe."""
    relay = await _connect(os.environ["NEUROX_LIVE_RELAY_URL"])
    try:
        rows = await relay.execute(
            "SELECT tenant_id FROM outbox_events WHERE event_id IN (%s, %s)",
            (two_tenants["a"]["event_id"], two_tenants["b"]["event_id"]),
        )
        assert {row[0] for row in await rows.fetchall()} == {
            two_tenants["a"]["tenant_id"],
            two_tenants["b"]["tenant_id"],
        }
    finally:
        await relay.close()


@pytest.mark.asyncio
async def test_the_relays_bypassrls_does_not_extend_to_business_data(
    two_tenants,
):
    """The one role where a bug becomes a leak. Test it hardest.

    The relay must be able to read the outbox across tenants to publish it,
    and must be able to read nothing else - otherwise a bug that joins an
    event to its case would put one tenant's data on another's queue.
    """
    relay = await _connect(os.environ["NEUROX_LIVE_RELAY_URL"])
    try:
        for table in ("cases", "documents", "extracted_fields", "vendors", "users"):
            with pytest.raises(
                (
                    psycopg.errors.InsufficientPrivilege,
                    psycopg.errors.UndefinedTable,
                )
            ):
                await relay.execute(f"SELECT * FROM {table} LIMIT 1")
    finally:
        await relay.close()


@pytest.mark.asyncio
async def test_an_events_payload_is_scoped_to_the_tenant_that_emitted_it(
    two_tenants,
):
    """Every outbox row must carry the tenant that owns it, and only that one."""
    relay = await _connect(os.environ["NEUROX_LIVE_RELAY_URL"])
    try:
        rows = await relay.execute(
            "SELECT tenant_id, payload FROM outbox_events WHERE event_id = %s",
            (two_tenants["a"]["event_id"],),
        )
        tenant_id, payload = (await rows.fetchall())[0]
        assert tenant_id == two_tenants["a"]["tenant_id"]
        assert str(two_tenants["b"]["case_id"]) not in str(payload), (
            "an event payload referenced another tenant's case"
        )
    finally:
        await relay.close()
