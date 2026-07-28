import asyncio
import uuid

from app.config import settings
from app.services.alerts import evaluate_alerts_for_tenant
from app.workers.database import WorkerSession, set_worker_tenant


def configured_tenant_ids() -> list[uuid.UUID]:
    configured = [
        item.strip()
        for item in settings.ALERT_TENANT_IDS.split(",")
        if item.strip()
    ]
    if not configured and settings.APP_ENV != "production":
        configured = [settings.DEV_TENANT_ID]
    return [uuid.UUID(item) for item in configured]


async def evaluate_once() -> None:
    for tenant_id in configured_tenant_ids():
        async with WorkerSession() as session:
            async with session.begin():
                await set_worker_tenant(session, str(tenant_id))
                await evaluate_alerts_for_tenant(
                    session, tenant_id=tenant_id
                )


async def run() -> None:
    if settings.APP_ENV == "production" and not configured_tenant_ids():
        raise RuntimeError("ALERT_TENANT_IDS_REQUIRED")
    while True:
        await evaluate_once()
        await asyncio.sleep(settings.ALERT_EVALUATION_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
