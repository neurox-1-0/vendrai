"""Provision the tenant and its role-separated users.

Runs as a Compose one-shot job before the workers start, so the stack comes up
with identities in place. It deliberately does *not* load reference data,
policies, or sanctions: those need the API and the retrieval worker running,
which they are not yet at this point in startup.

Everything else is `python -m scripts.bootstrap`, which shares this module's
identity definitions so the two cannot disagree about who exists.
"""

import asyncio
import uuid

from app.config import settings
from app.database import AsyncSessionLocal, set_tenant_context

from scripts.bootstrap.identities import ensure_tenant, ensure_users


async def seed() -> None:
    tenant_id = uuid.UUID(settings.DEV_TENANT_ID)
    async with AsyncSessionLocal() as session, session.begin():
        await set_tenant_context(session, str(tenant_id))
        await ensure_tenant(session, tenant_id)
        count = await ensure_users(session, tenant_id)
    print(f"Seeded tenant {tenant_id} with {count} role-separated users.")
    print("Run './scripts/stack.sh bootstrap' to load reference data and policies.")


if __name__ == "__main__":
    asyncio.run(seed())
