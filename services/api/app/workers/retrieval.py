import asyncio
import uuid

from app.models import InboxReceipt, PolicyChunk, PolicyDocument, PolicyVersion
from app.retrieval import index_chunks
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from sqlalchemy import select


async def index_policy(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    policy_version_id = uuid.UUID(envelope["payload"]["policy_version_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "retrieval-worker", "event_id": event_id}):
                return
            rows = (await session.execute(
                select(PolicyChunk, PolicyVersion, PolicyDocument)
                .join(PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.policy_version_id)
                .join(PolicyDocument, PolicyVersion.policy_document_id == PolicyDocument.policy_document_id)
                .where(PolicyChunk.policy_version_id == policy_version_id, PolicyChunk.tenant_id == tenant_id, PolicyVersion.status == "PUBLISHED")
            )).all()
            payloads = []
            for chunk, version, document in rows:
                payloads.append({
                    "point_id": str(chunk.policy_chunk_id), "tenant_id": str(tenant_id),
                    "policy_version_id": str(version.policy_version_id), "policy_code": document.policy_code,
                    "version": version.version, "effective_date": version.effective_date, "status": version.status,
                    "department": document.owner_department, "acl": chunk.acl, "clause_id": chunk.clause_id,
                    "heading_path": chunk.heading_path, "content": chunk.content, "parent_content": chunk.parent_content,
                })
            await asyncio.to_thread(index_chunks, payloads)
            for chunk, _version, _document in rows:
                chunk.qdrant_point_id = str(chunk.policy_chunk_id)
            session.add(InboxReceipt(consumer_name="retrieval-worker", event_id=event_id, tenant_id=tenant_id))


if __name__ == "__main__":
    asyncio.run(consume("retrieval-worker", ["policy.published.v1"], index_policy))
