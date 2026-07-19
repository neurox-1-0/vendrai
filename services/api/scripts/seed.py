import asyncio
import uuid

from app.config import settings
from app.database import AsyncSessionLocal, set_tenant_context
from app.models import Tenant, User


async def seed() -> None:
    tenant_id = uuid.UUID(settings.DEV_TENANT_ID)
    users = [
        (uuid.UUID(settings.DEV_USER_ID), "requester@neurox.local", "Demo Requester", ["requester"]),
        (uuid.UUID("00000000-0000-0000-0000-000000000102"), "analyst@neurox.local", "Demo Analyst", ["analyst"]),
        (uuid.UUID("00000000-0000-0000-0000-000000000103"), "approver@neurox.local", "Demo Approver", ["approver"]),
        (uuid.UUID("00000000-0000-0000-0000-000000000104"), "auditor@neurox.local", "Demo Auditor", ["auditor", "admin"]),
    ]
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_context(session, str(tenant_id))
            if not await session.get(Tenant, tenant_id):
                session.add(Tenant(tenant_id=tenant_id, name="NeuroX Demo", slug="neurox-demo"))
                await session.flush()
            for user_id, email, name, roles in users:
                if not await session.get(User, user_id):
                    session.add(User(
                        user_id=user_id, tenant_id=tenant_id, external_subject=f"seed:{user_id}",
                        email=email, full_name=name, roles=roles,
                    ))


if __name__ == "__main__":
    asyncio.run(seed())
