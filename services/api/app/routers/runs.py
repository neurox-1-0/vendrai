import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, CurrentPrincipal
from app.database import AsyncSessionLocal, get_db, set_tenant_context
from app.domain.pii import mask_sensitive_text
from app.models import AgentRun, AgentStep, Case, CaseEvent
from app.schemas import (
    AgentStepResponse,
    EventResponse,
    RunDiagnosticsResponse,
    RunGraphEdge,
    RunGraphResponse,
    RunResponse,
    RunTimingSummary,
)

router = APIRouter(tags=["runs", "events"])
Db = Annotated[AsyncSession, Depends(get_db)]

DISPLAY_NAMES = {
    "goal_planner": "Goal planner",
    "document_processing": "Document scan and OCR",
    "document_intelligence": "Document intelligence",
    "duplicate_detection": "Duplicate detection",
    "sanctions_screening": "Sanctions screening",
    "policy_retrieval": "Policy research",
    "po_retrieval": "Purchase order retrieval",
    "grn_retrieval": "Goods receipt retrieval",
    "vendor_resolution": "Vendor resolution",
    "duplicate_invoice": "Duplicate invoice detection",
    "bank_consistency": "Bank consistency",
    "three_way_match": "Three-way match",
    "gemini_contradiction": "Contradiction reasoning",
    "deterministic_verification": "Evidence verifier",
    "gemini_evidence_critique": "Evidence critique",
    "control_review": "Human control review",
    "human_gate": "Final human approval",
    "erp_confirmation": "ERP confirmation",
}

DEFAULT_DEPENDENCIES = {
    "document_intelligence": ["document_processing"],
    "goal_planner": ["document_intelligence"],
    "duplicate_detection": ["document_intelligence"],
    "sanctions_screening": ["document_intelligence"],
    "policy_retrieval": ["goal_planner"],
    "po_retrieval": ["goal_planner"],
    "grn_retrieval": ["po_retrieval"],
    "vendor_resolution": ["document_intelligence"],
    "duplicate_invoice": ["vendor_resolution"],
    "bank_consistency": ["document_intelligence", "vendor_resolution"],
    "three_way_match": ["document_intelligence", "po_retrieval", "grn_retrieval"],
    "gemini_contradiction": [
        "duplicate_detection",
        "sanctions_screening",
        "policy_retrieval",
        "three_way_match",
    ],
    "deterministic_verification": ["gemini_contradiction"],
    "gemini_evidence_critique": ["deterministic_verification"],
    "control_review": ["gemini_evidence_critique"],
    "human_gate": ["gemini_evidence_critique", "control_review"],
    "erp_confirmation": ["human_gate"],
}

SENSITIVE_DIAGNOSTIC_KEYS = {
    "bank_account",
    "document_bytes",
    "document_path",
    "email",
    "phone",
    "presigned_url",
    "raw_document",
    "raw_ocr",
    "sql",
    "statement",
    "swift_code",
    "tax_id",
    "token",
}


def _agent_kind(node_name: str) -> str:
    if node_name == "goal_planner":
        return "PLANNER"
    if node_name in {"gemini_contradiction", "gemini_evidence_critique"}:
        return "REASONING"
    if node_name == "deterministic_verification":
        return "VERIFIER"
    if node_name in {"control_review", "human_gate"}:
        return "HUMAN"
    if node_name == "erp_confirmation":
        return "EXECUTION"
    return "SPECIALIST"


def _sanitize(value):
    if isinstance(value, dict):
        return {
            str(key): (
                "<REDACTED>"
                if str(key).lower() in SENSITIVE_DIAGNOSTIC_KEYS
                else _sanitize(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, str):
        return mask_sensitive_text(value)
    return value


async def _authorized_run(
    run_id: uuid.UUID,
    db: AsyncSession,
    principal,
) -> AgentRun:
    principal.require_any(*CASE_READ_ROLES)
    run = await db.scalar(
        select(AgentRun).where(
            AgentRun.run_id == run_id,
            AgentRun.tenant_id == principal.tenant_id,
        )
    )
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


def _dependencies(step: AgentStep, available_names: set[str]) -> list[str]:
    explicit = step.input_summary.get("dependencies", [])
    candidates = explicit if isinstance(explicit, list) else []
    if not candidates:
        candidates = DEFAULT_DEPENDENCIES.get(step.node_name, [])
    return [
        str(candidate)
        for candidate in candidates
        if str(candidate) in available_names
    ]


def _step_response(
    step: AgentStep,
    available_names: set[str],
) -> AgentStepResponse:
    started_at = step.created_at
    recorded_start = step.input_summary.get("started_at")
    if isinstance(recorded_start, str):
        try:
            started_at = datetime.fromisoformat(recorded_start)
        except ValueError:
            pass
    completed_at = None
    recorded_completion = step.output_summary.get("completed_at")
    if isinstance(recorded_completion, str):
        try:
            completed_at = datetime.fromisoformat(recorded_completion)
        except ValueError:
            pass
    if (
        completed_at is None
        and step.latency_ms is not None
        and step.status not in {"QUEUED", "RUNNING"}
    ):
        completed_at = started_at + timedelta(milliseconds=step.latency_ms)
    route_reason = step.input_summary.get("route_reason")
    if not isinstance(route_reason, str) or not route_reason.strip():
        route_reason = "Selected by the validated workflow plan."
    return AgentStepResponse(
        step_id=step.step_id,
        run_id=step.run_id,
        node_name=step.node_name,
        display_name=DISPLAY_NAMES.get(
            step.node_name,
            step.node_name.replace("_", " ").title(),
        ),
        agent_kind=_agent_kind(step.node_name),
        attempt=step.attempt,
        status=step.status,
        route_reason=route_reason,
        dependencies=_dependencies(step, available_names),
        input_summary=_sanitize(step.input_summary),
        output_summary=_sanitize(step.output_summary),
        error=_sanitize(step.error),
        latency_ms=step.latency_ms,
        started_at=started_at,
        completed_at=completed_at,
    )


async def _run_graph(
    run: AgentRun,
    db: AsyncSession,
) -> RunGraphResponse:
    rows = (
        await db.execute(
            select(AgentStep)
            .where(
                AgentStep.run_id == run.run_id,
                AgentStep.tenant_id == run.tenant_id,
            )
            .order_by(AgentStep.created_at, AgentStep.node_name, AgentStep.attempt)
        )
    ).scalars().all()
    available_names = {step.node_name for step in rows}
    nodes = [_step_response(step, available_names) for step in rows]
    nodes.sort(key=lambda node: (node.started_at, node.node_name, node.attempt))
    latest_node_ids: dict[str, str] = {}
    for node in nodes:
        latest_node_ids[node.node_name] = str(node.step_id)
    edges = [
        RunGraphEdge(
            source=latest_node_ids[dependency],
            target=str(node.step_id),
        )
        for node in nodes
        for dependency in node.dependencies
        if dependency in latest_node_ids
        and latest_node_ids[dependency] != str(node.step_id)
    ]

    active_compute_ms = sum(node.latency_ms or 0 for node in nodes)
    critical_by_name: dict[str, int] = {}
    for node in nodes:
        dependency_duration = max(
            (
                critical_by_name.get(dependency, 0)
                for dependency in node.dependencies
            ),
            default=0,
        )
        critical_by_name[node.node_name] = max(
            critical_by_name.get(node.node_name, 0),
            dependency_duration + (node.latency_ms or 0),
        )
    critical_path_ms = max(critical_by_name.values(), default=0)
    now = datetime.now(UTC)
    if run.started_at and run.started_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    end = run.completed_at or (now if run.started_at else None)
    total_elapsed_ms = (
        max(0, round((end - run.started_at).total_seconds() * 1000))
        if end and run.started_at
        else None
    )
    state = run.state_json if isinstance(run.state_json, dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    objective = str(
        plan.get("objective")
        or (
            "Resolve an invoice exception with verified evidence."
            if run.graph_name == "invoice_exception"
            else "Onboard a supplier with verified evidence."
        )
    )
    return RunGraphResponse(
        run=RunResponse.model_validate(run),
        objective=objective,
        selected_path=[node.node_name for node in nodes],
        plan=_sanitize(plan),
        nodes=nodes,
        edges=edges,
        timing=RunTimingSummary(
            total_elapsed_ms=total_elapsed_ms,
            active_compute_ms=active_compute_ms,
            critical_path_ms=critical_path_ms,
            parallel_time_saved_ms=max(
                0,
                active_compute_ms - critical_path_ms,
            ),
            human_waiting_ms=None,
        ),
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    return await _authorized_run(run_id, db, principal)


@router.get(
    "/runs/{run_id}/steps",
    response_model=list[AgentStepResponse],
)
async def get_run_steps(
    run_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    run = await _authorized_run(run_id, db, principal)
    return (await _run_graph(run, db)).nodes


@router.get(
    "/runs/{run_id}/graph",
    response_model=RunGraphResponse,
)
async def get_run_graph(
    run_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    run = await _authorized_run(run_id, db, principal)
    return await _run_graph(run, db)


@router.get(
    "/runs/{run_id}/diagnostics",
    response_model=RunDiagnosticsResponse,
)
async def get_run_diagnostics(
    run_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any("auditor", "admin")
    run = await _authorized_run(run_id, db, principal)
    graph = await _run_graph(run, db)
    state = run.state_json if isinstance(run.state_json, dict) else {}
    allowed_state_keys = {
        "blocker",
        "completed_reviews",
        "current_stage",
        "evidence_hash",
        "outcome",
        "plan",
        "reason_codes",
        "recommendation",
        "required_reviews",
        "verification_result",
    }
    decision_summary = {
        key: _sanitize(state[key])
        for key in allowed_state_keys
        if key in state
    }
    evidence_hash = state.get("evidence_hash") or run.input_hash
    return RunDiagnosticsResponse(
        graph=graph,
        versions={
            "graph_name": run.graph_name,
            "graph_version": run.graph_version,
            "model_name": run.model_name,
            "prompt_version": run.prompt_version,
        },
        integrity={
            "evidence_hash": (
                str(evidence_hash) if evidence_hash else None
            ),
            "state_version": run.state_version,
            "tenant_scoped": True,
            "private_reasoning_persisted": False,
        },
        decision_summary=decision_summary,
    )


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
