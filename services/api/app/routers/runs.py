import asyncio
import json
import uuid
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, CurrentPrincipal
from app.database import AsyncSessionLocal, get_db, set_tenant_context
from app.models import AgentRun, Case, CaseEvent
from app.schemas import EventResponse, RunResponse

router = APIRouter(tags=["runs", "events"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    principal.require_any(*CASE_READ_ROLES)
    run = await db.scalar(select(AgentRun).where(AgentRun.run_id == run_id, AgentRun.tenant_id == principal.tenant_id))
    if not run:
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
    case = await db.get(Case, run.case_id)
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
    return run


@router.get("/cases/{case_id}/events", response_model=list[EventResponse])
async def list_case_events(case_id: uuid.UUID, db: Db, principal: CurrentPrincipal, after: int = 0):
    principal.require_any(*CASE_READ_ROLES)
    case = await db.scalar(select(Case).where(Case.case_id == case_id, Case.tenant_id == principal.tenant_id))
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return list((await db.execute(
        select(CaseEvent).where(CaseEvent.case_id == case_id, CaseEvent.tenant_id == principal.tenant_id, CaseEvent.sequence > after).order_by(CaseEvent.sequence)
    )).scalars().all())


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    principal.require_any(*CASE_READ_ROLES)
    async with AsyncSessionLocal() as verify_session:
        async with verify_session.begin():
            await set_tenant_context(verify_session, str(principal.tenant_id))
            run = await verify_session.scalar(select(AgentRun).where(AgentRun.run_id == run_id, AgentRun.tenant_id == principal.tenant_id))
            if not run:
                raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
            case_id = run.case_id
            case = await verify_session.get(Case, case_id)
            if (
                not case
                or principal.is_requester_only
                and case.requester_user_id != principal.user_id
            ):
                raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
    try:
        cursor = int(last_event_id or 0)
    except ValueError:
        cursor = 0

    async def generate() -> AsyncIterator[str]:
        nonlocal cursor
        while not await request.is_disconnected():
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await set_tenant_context(session, str(principal.tenant_id))
                    events = (await session.execute(
                        select(CaseEvent).where(CaseEvent.case_id == case_id, CaseEvent.sequence > cursor).order_by(CaseEvent.sequence).limit(100)
                    )).scalars().all()
            for event in events:
                cursor = event.sequence
                payload = {"type": event.event_type, "case_id": str(case_id), "sequence": cursor, "payload": event.payload, "created_at": event.created_at.isoformat()}
                yield f"id: {cursor}\nevent: {event.event_type}\ndata: {json.dumps(payload)}\n\n"
            if not events:
                yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
