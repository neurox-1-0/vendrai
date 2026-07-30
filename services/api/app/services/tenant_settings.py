"""Read and write a tenant's business thresholds.

Callers get a validated :class:`TenantConfiguration` whether or not a row
exists, so no control has to handle "unconfigured" as a special case. That
matters more than it sounds: a control that silently skips itself when
configuration is missing is a control that does not run.
"""

from __future__ import annotations

import uuid

from app.domain.tenant_config import TenantConfiguration
from app.models import TenantConfigurationRecord
from sqlalchemy.ext.asyncio import AsyncSession


async def get_tenant_configuration(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> TenantConfiguration:
    """Return the tenant's configuration, falling back to the defaults.

    A stored document that no longer validates against the current schema
    falls back to defaults rather than raising: a schema change must not take
    every control offline. The mismatch is visible through the settings API,
    which validates on write.
    """
    record = await session.get(TenantConfigurationRecord, tenant_id)
    if record is None or not record.configuration:
        return TenantConfiguration()
    try:
        return TenantConfiguration.model_validate(record.configuration)
    except ValueError:
        return TenantConfiguration()


async def set_tenant_configuration(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    configuration: TenantConfiguration,
    *,
    updated_by: uuid.UUID | None = None,
) -> TenantConfigurationRecord:
    record = await session.get(TenantConfigurationRecord, tenant_id)
    if record is None:
        record = TenantConfigurationRecord(tenant_id=tenant_id, version=0)
        session.add(record)
    record.configuration = configuration.model_dump(mode="json")
    record.version += 1
    record.updated_by = updated_by
    await session.flush()
    return record
