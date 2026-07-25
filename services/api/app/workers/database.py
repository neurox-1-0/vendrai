from app.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

worker_engine = create_async_engine(settings.WORKER_DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
WorkerSession = async_sessionmaker(worker_engine, expire_on_commit=False, autoflush=False)


async def set_worker_tenant(session: AsyncSession, tenant_id: str) -> None:
    """Set tenant context before any worker-owned table access in this transaction."""
    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(
            text(
                "SELECT set_config("
                "'app.current_tenant_id', :tenant_id, true)"
            ),
            {"tenant_id": tenant_id},
        )
