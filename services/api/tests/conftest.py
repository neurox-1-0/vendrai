import os

os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "development"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/neurox-api-tests.db"
os.environ["LOCAL_STORAGE_ROOT"] = "/tmp/neurox-api-test-objects"

import pytest_asyncio

from app.database import Base, engine


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
