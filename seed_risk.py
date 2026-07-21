import asyncio
from uuid import UUID
from datetime import datetime

from app.database import AsyncSessionLocal, set_tenant_context
from app.models import SanctionsDataset, SanctionsEntityRecord
from sqlalchemy import select

async def seed_risk():
    async with AsyncSessionLocal() as session:
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        await set_tenant_context(session, str(tenant_id))
        
        # Check if dataset exists
        stmt = select(SanctionsDataset).where(SanctionsDataset.source == "OFAC_MOCK")
        res = await session.execute(stmt)
        dataset = res.scalars().first()
        
        if not dataset:
            dataset = SanctionsDataset(
                source="OFAC_MOCK",
                version="2026.07.21",
                source_url="http://mock.example.com",
                sha256="mockhash123",
                status="PUBLISHED",
                published_at=datetime.utcnow()
            )
            session.add(dataset)
            await session.commit()
            await session.refresh(dataset)
        
        # Seed Harborline
        stmt = select(SanctionsEntityRecord).where(SanctionsEntityRecord.primary_name == "Harborline Logistics (Pvt) Ltd")
        res = await session.execute(stmt)
        if not res.scalars().first():
            entity = SanctionsEntityRecord(
                dataset_id=dataset.dataset_id,
                external_id="MOCK-001",
                primary_name="Harborline Logistics (Pvt) Ltd",
                normalized_name="harborline logistics (pvt) ltd",
                aliases=[],
                countries=["US"]
            )
            session.add(entity)
        
        await session.commit()
        print("Risk data seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_risk())
