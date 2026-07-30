import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, CurrentPrincipal
from app.database import get_db
from app.domain.chunking import chunk_policy
from app.domain.security import canonical_hash
from app.models import PolicyChunk, PolicyDocument, PolicyVersion
from app.schemas import PolicyResponse, PolicyUploadRequest
from app.services.events import append_audit, enqueue_event

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/documents", response_model=list[PolicyResponse])
async def list_policies(
    db: Db,
    principal: CurrentPrincipal,
    policy_code: str | None = None,
):
    """List the tenant's policies and the state of their latest version.

    Read access is broad on purpose: every staff role reviews cases against
    cited policy, and a reviewer who cannot see which version is in force
    cannot judge the citation.
    """
    principal.require_any(*CASE_READ_ROLES)
    query = select(PolicyDocument).where(PolicyDocument.tenant_id == principal.tenant_id)
    if policy_code:
        query = query.where(PolicyDocument.policy_code == policy_code)
    documents = (await db.execute(query.order_by(PolicyDocument.policy_code))).scalars().all()

    responses: list[PolicyResponse] = []
    for document in documents:
        version = await db.scalar(
            select(PolicyVersion)
            .where(PolicyVersion.policy_document_id == document.policy_document_id)
            .order_by(
                # A published version is what a citation resolves against, so
                # report that in preference to a newer draft.
                (PolicyVersion.status == "PUBLISHED").desc(),
                PolicyVersion.published_at.desc().nulls_last(),
                PolicyVersion.created_at.desc(),
            )
            .limit(1)
        )
        if version is None:
            continue
        chunk_count = await db.scalar(
            select(func.count())
            .select_from(PolicyChunk)
            .where(PolicyChunk.policy_version_id == version.policy_version_id)
        )
        responses.append(
            PolicyResponse(
                policy_document_id=document.policy_document_id,
                policy_version_id=version.policy_version_id,
                policy_code=document.policy_code,
                title=document.title,
                version=version.version,
                status=version.status,
                chunk_count=int(chunk_count or 0),
            )
        )
    return responses


@router.post("/documents", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: PolicyUploadRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
):
    principal.require_any("admin")
    existing = await db.scalar(select(PolicyDocument).where(
        PolicyDocument.tenant_id == principal.tenant_id, PolicyDocument.policy_code == body.policy_code,
    ))
    if existing:
        raise HTTPException(409, detail={"code": "POLICY_ALREADY_EXISTS"})
    document = PolicyDocument(
        tenant_id=principal.tenant_id, policy_code=body.policy_code, title=body.title,
        owner_department=body.owner_department, status="DRAFT",
    )
    db.add(document)
    await db.flush()
    version = PolicyVersion(
        tenant_id=principal.tenant_id, policy_document_id=document.policy_document_id,
        version=body.version, effective_date=body.effective_date,
        content_hash=canonical_hash(body.content), status="DRAFT",
    )
    db.add(version)
    await db.flush()
    chunks = chunk_policy(body.content)
    for chunk in chunks:
        db.add(PolicyChunk(
            tenant_id=principal.tenant_id, policy_version_id=version.policy_version_id,
            clause_id=chunk.clause_id, heading_path=chunk.heading_path, parent_content=chunk.parent_content,
            content=chunk.content, token_count=chunk.token_count, acl=["requester", "analyst", "approver", "auditor", "admin"],
        ))
    await append_audit(
        db, tenant_id=principal.tenant_id, case_id=None, actor_type="USER", actor_id=str(principal.user_id),
        action="POLICY_CREATED", resource_type="POLICY_VERSION", resource_id=str(version.policy_version_id),
        metadata={"policy_code": body.policy_code, "version": body.version, "chunk_count": len(chunks)},
    )
    return PolicyResponse(
        policy_document_id=document.policy_document_id, policy_version_id=version.policy_version_id,
        policy_code=document.policy_code, title=document.title, version=version.version,
        status=version.status, chunk_count=len(chunks),
    )


@router.post("/documents/{policy_version_id}:publish", response_model=PolicyResponse)
async def publish_policy(
    policy_version_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
):
    principal.require_any("admin")
    version = await db.scalar(select(PolicyVersion).where(
        PolicyVersion.policy_version_id == policy_version_id, PolicyVersion.tenant_id == principal.tenant_id,
    ).with_for_update())
    if not version:
        raise HTTPException(404, detail={"code": "POLICY_VERSION_NOT_FOUND"})
    document = await db.get(PolicyDocument, version.policy_document_id)
    chunks = (await db.execute(select(PolicyChunk).where(PolicyChunk.policy_version_id == policy_version_id))).scalars().all()
    if not chunks:
        raise HTTPException(409, detail={"code": "POLICY_HAS_NO_CHUNKS"})
    version.status = "PUBLISHED"
    version.published_at = datetime.now(UTC)
    document.status = "PUBLISHED"
    enqueue_event(
        db, tenant_id=principal.tenant_id, aggregate_type="policy", aggregate_id=policy_version_id,
        aggregate_version=1, event_type="policy.published.v1",
        idempotency_key=f"policy.publish:{policy_version_id}:{idempotency_key}",
        payload={"policy_version_id": str(policy_version_id), "chunk_count": len(chunks)},
    )
    return PolicyResponse(
        policy_document_id=document.policy_document_id, policy_version_id=version.policy_version_id,
        policy_code=document.policy_code, title=document.title, version=version.version,
        status=version.status, chunk_count=len(chunks),
    )
