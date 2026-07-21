import asyncio
import csv
from uuid import UUID, uuid4
from datetime import datetime

from app.database import AsyncSessionLocal, set_tenant_context
from app.models import Vendor, InvoiceRecord, Tenant
from sqlalchemy import select

async def seed_data():
    async with AsyncSessionLocal() as session:
        # Default tenant
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        await set_tenant_context(session, str(tenant_id))
        
        # Load vendors
        with open("/tmp/ground_truth/existing_vendor_master.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                erp_vendor_id = row["vendor_id"]
                # check if exists
                stmt = select(Vendor).where(Vendor.tenant_id == tenant_id, Vendor.erp_vendor_id == erp_vendor_id)
                res = await session.execute(stmt)
                if not res.scalars().first():
                    vendor = Vendor(
                        tenant_id=tenant_id,
                        legal_name=row["legal_name"],
                        normalized_legal_name=row["legal_name"].lower(),
                        erp_vendor_id=erp_vendor_id,
                        status=row["status"]
                    )
                    session.add(vendor)
        
        await session.commit()
        
        # We need the inserted vendors to link invoices
        vendor_map = {}
        stmt = select(Vendor).where(Vendor.tenant_id == tenant_id)
        res = await session.execute(stmt)
        for v in res.scalars().all():
            vendor_map[v.erp_vendor_id] = v.vendor_id

        # Load invoices
        with open("/tmp/ground_truth/existing_invoice_history.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                v_erp_id = row["vendor_id"]
                v_uuid = vendor_map.get(v_erp_id)
                if not v_uuid:
                    continue
                
                stmt = select(InvoiceRecord).where(InvoiceRecord.tenant_id == tenant_id, InvoiceRecord.invoice_number == row["invoice_number"], InvoiceRecord.vendor_id == v_uuid)
                res = await session.execute(stmt)
                if not res.scalars().first():
                    inv = InvoiceRecord(
                        tenant_id=tenant_id,
                        vendor_id=v_uuid,
                        invoice_number=row["invoice_number"],
                        po_number=row["po_number"],
                        invoice_date=datetime.strptime(row["invoice_date"], "%Y-%m-%d"),
                        total_amount=float(row["gross_amount"]),
                        currency=row["currency"],
                        status=row["status"]
                    )
                    session.add(inv)
        
        await session.commit()
        print("Seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_data())
