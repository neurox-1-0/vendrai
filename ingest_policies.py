import asyncio
from uuid import UUID, uuid4
from datetime import datetime
import PyPDF2

from app.database import AsyncSessionLocal, set_tenant_context
from app.models import PolicyDocument, PolicyVersion, PolicyChunk, InboxReceipt
from app.domain.chunking import chunk_policy
from app.domain.security import canonical_hash
from sqlalchemy import select

def extract_text(pdf_path):
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"
        return text

async def seed_policies():
    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    
    policies = [
        {
            "path": "/tmp/knowledge_base/AP-001_Invoice_Matching_and_Exception_Policy.pdf",
            "code": "AP-001",
            "title": "Invoice Matching and Exception Policy",
            "dept": "Finance",
            "version": "1.0",
            "effective": "2026-01-01"
        },
        {
            "path": "/tmp/knowledge_base/PROC-001_Supplier_Onboarding_Policy.pdf",
            "code": "PROC-001",
            "title": "Supplier Onboarding Policy",
            "dept": "Procurement",
            "version": "1.0",
            "effective": "2026-01-01"
        }
    ]

    async with AsyncSessionLocal() as session:
        await set_tenant_context(session, str(tenant_id))
        
        for p in policies:
            # Check existing
            existing = await session.scalar(select(PolicyDocument).where(
                PolicyDocument.tenant_id == tenant_id, PolicyDocument.policy_code == p["code"]
            ))
            if existing:
                print(f"{p['code']} already exists, skipping")
                continue
            
            text = extract_text(p["path"])
            
            doc = PolicyDocument(
                tenant_id=tenant_id, policy_code=p["code"], title=p["title"],
                owner_department=p["dept"], status="PUBLISHED"
            )
            session.add(doc)
            await session.flush()
            
            ver = PolicyVersion(
                tenant_id=tenant_id, policy_document_id=doc.policy_document_id,
                version=p["version"], effective_date=p["effective"],
                content_hash=canonical_hash(text), status="PUBLISHED",
                published_at=datetime.utcnow()
            )
            session.add(ver)
            await session.flush()
            
            chunks = chunk_policy(text)
            for chunk in chunks:
                session.add(PolicyChunk(
                    tenant_id=tenant_id, policy_version_id=ver.policy_version_id,
                    clause_id=chunk.clause_id, heading_path=chunk.heading_path, parent_content=chunk.parent_content,
                    content=chunk.content, token_count=chunk.token_count, acl=["requester", "analyst", "approver", "auditor", "admin"]
                ))
            
            # Send message to retrieval worker to index
            from app.services.events import enqueue_event
            enqueue_event(
                session,
                tenant_id=tenant_id,
                aggregate_type="POLICY",
                aggregate_id=doc.policy_document_id,
                aggregate_version=1,
                event_type="policy.published.v1",
                idempotency_key=str(uuid4()),
                payload={"policy_version_id": str(ver.policy_version_id)}
            )
            
            print(f"Ingested {p['code']}")
            
        await session.commit()
        print("Done")

if __name__ == "__main__":
    asyncio.run(seed_policies())
