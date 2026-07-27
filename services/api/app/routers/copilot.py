import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CASE_READ_ROLES, CurrentPrincipal, Principal
from app.config import settings
from app.copilot import (
    HELP_PACK_VERSION,
    CopilotDraft,
    SafeAction,
    allowed_actions,
    attempts_business_mutation,
    retrieve_help,
)
from app.database import get_db
from app.domain.pii import mask_sensitive_text
from app.domain.security import canonical_hash
from app.llm_gateway import LLMProviderError
from app.llm_gateway import structured_reasoning_with_metadata as call_llm
from app.models import (
    AgentRun,
    Case,
    CopilotFeedback,
    CopilotMessage,
    CopilotSession,
    Document,
    IdempotencyRecord,
)
from app.schemas import (
    CopilotCitation,
    CopilotFeedbackRequest,
    CopilotFeedbackResponse,
    CopilotMessageRequest,
    CopilotMessageResponse,
    CopilotSessionCreate,
    CopilotSessionResponse,
    CopilotUIAction,
)
from app.services.events import append_audit

router = APIRouter(prefix="/copilot", tags=["copilot"])
Db = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


async def _authorized_case(
    db: AsyncSession,
    principal: Principal,
    case_id: uuid.UUID,
) -> Case:
    case = await db.scalar(
        select(Case).where(
            Case.case_id == case_id,
            Case.tenant_id == principal.tenant_id,
        )
    )
    if (
        not case
        or principal.is_requester_only
        and case.requester_user_id != principal.user_id
    ):
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"})
    return case


async def _authorized_session(
    db: AsyncSession,
    principal: Principal,
    session_id: uuid.UUID,
) -> CopilotSession:
    session = await db.scalar(
        select(CopilotSession).where(
            CopilotSession.copilot_session_id == session_id,
            CopilotSession.tenant_id == principal.tenant_id,
            CopilotSession.user_id == principal.user_id,
        )
    )
    if not session:
        raise HTTPException(404, detail={"code": "COPILOT_SESSION_NOT_FOUND"})
    return session


def _response(message: CopilotMessage) -> CopilotMessageResponse:
    return CopilotMessageResponse(
        copilot_message_id=message.copilot_message_id,
        copilot_session_id=message.copilot_session_id,
        role=message.role,
        content=message.content_masked,
        citations=[
            CopilotCitation.model_validate(item)
            for item in message.citations
        ],
        ui_actions=[
            CopilotUIAction.model_validate(item)
            for item in message.ui_actions
        ],
        provider=message.provider,
        model_version=message.model_version,
        latency_ms=message.latency_ms,
        error_code=message.error_code,
        created_at=message.created_at,
    )


async def _case_context(
    db: AsyncSession,
    principal: Principal,
    case_id: uuid.UUID | None,
) -> dict[str, Any]:
    if not case_id:
        return {}
    case = await _authorized_case(db, principal, case_id)
    run = await db.scalar(
        select(AgentRun)
        .where(
            AgentRun.case_id == case.case_id,
            AgentRun.tenant_id == principal.tenant_id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    documents = (
        await db.execute(
            select(Document).where(
                Document.case_id == case.case_id,
                Document.tenant_id == principal.tenant_id,
            )
        )
    ).scalars().all()
    state = run.state_json if run and isinstance(run.state_json, dict) else {}
    reason_codes = state.get("reason_codes", [])
    if not isinstance(reason_codes, list):
        reason_codes = []
    return {
        "case_type": case.case_type,
        "case_status": case.status,
        "case_version": case.current_version,
        "assigned_to_current_user": case.assigned_user_id
        == principal.user_id,
        "document_statuses": sorted(
            {
                document.processing_status
                for document in documents
            }
        ),
        "run_status": run.status if run else None,
        "current_node": run.current_node if run else None,
        "reason_codes": [
            str(code)[:100] for code in reason_codes[:12]
        ],
    }


def _screen_key(current_path: str) -> str:
    if current_path.startswith("/cases/"):
        return "/cases/{case_id}"
    return current_path.split("?", 1)[0]


def _fallback_answer(
    entries,
    *,
    mutation_requested: bool,
) -> str:
    prefix = ""
    if mutation_requested:
        prefix = (
            "I can explain and guide you, but I cannot submit, approve, reject, "
            "change evidence, resolve sanctions, or trigger ERP actions. "
        )
    if not entries:
        return (
            prefix
            + "I could not find a supported help topic for that question. "
            "Try asking how to start a workflow, read the execution map, resolve "
            "a clarification, or inspect a failed step."
        )
    return prefix + " ".join(entry.content for entry in entries[:2])


@router.post(
    "/sessions",
    response_model=CopilotSessionResponse,
    status_code=201,
)
async def create_session(
    request: CopilotSessionCreate,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    principal.require_any(*CASE_READ_ROLES)
    if request.case_id:
        await _authorized_case(db, principal, request.case_id)
    scope = f"copilot.session:{principal.user_id}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = canonical_hash(request.model_dump(mode="json"))
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == principal.tenant_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(
                409,
                detail={"code": "IDEMPOTENCY_KEY_REUSED"},
            )
        existing_session = await db.get(
            CopilotSession,
            existing.resource_id,
        )
        if existing_session and existing_session.user_id == principal.user_id:
            return existing_session
    session = CopilotSession(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        context_case_id=request.case_id,
        help_pack_version=HELP_PACK_VERSION,
    )
    db.add(session)
    await db.flush()
    db.add(
        IdempotencyRecord(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            resource_id=session.copilot_session_id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=request.case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="COPILOT_SESSION_CREATED",
        resource_type="COPILOT_SESSION",
        resource_id=str(session.copilot_session_id),
        metadata={
            "help_pack_version": HELP_PACK_VERSION,
            "current_path": request.current_path,
        },
    )
    return session


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[CopilotMessageResponse],
)
async def list_messages(
    session_id: uuid.UUID,
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any(*CASE_READ_ROLES)
    await _authorized_session(db, principal, session_id)
    messages = (
        await db.execute(
            select(CopilotMessage)
            .where(
                CopilotMessage.copilot_session_id == session_id,
                CopilotMessage.tenant_id == principal.tenant_id,
            )
            .order_by(CopilotMessage.created_at, CopilotMessage.copilot_message_id)
        )
    ).scalars().all()
    return [_response(message) for message in messages]


@router.post(
    "/sessions/{session_id}/messages",
    response_model=CopilotMessageResponse,
)
async def send_message(
    session_id: uuid.UUID,
    request: CopilotMessageRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    principal.require_any(*CASE_READ_ROLES)
    session = await _authorized_session(db, principal, session_id)
    scope = f"copilot.message:{session_id}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = canonical_hash(request.model_dump(mode="json"))
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == principal.tenant_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(
                409,
                detail={"code": "IDEMPOTENCY_KEY_REUSED"},
            )
        existing_message = await db.get(
            CopilotMessage,
            existing.resource_id,
        )
        if (
            existing_message
            and existing_message.copilot_session_id == session_id
        ):
            return _response(existing_message)
    context_case_id = request.case_id or session.context_case_id
    if context_case_id:
        await _authorized_case(db, principal, context_case_id)
        session.context_case_id = context_case_id
    masked_question = mask_sensitive_text(request.question)
    user_message = CopilotMessage(
        tenant_id=principal.tenant_id,
        copilot_session_id=session.copilot_session_id,
        role="USER",
        content_masked=masked_question,
        provider="LOCAL_INPUT",
    )
    db.add(user_message)
    await db.flush()

    entries = retrieve_help(
        masked_question,
        request.current_path,
        principal,
    )
    action_registry = allowed_actions(entries, principal)
    for target in request.assistance_targets:
        action_id = f"spotlight::{target.target_id}"
        action_registry[action_id] = SafeAction(
            action_id=action_id,
            action_type="SPOTLIGHT",
            target=target.target_id,
            label=f"Show {target.title}",
            roles=frozenset(principal.roles),
        )
    citations = [
        {
            "source_id": entry.source_id,
            "title": entry.title,
            "help_pack_version": HELP_PACK_VERSION,
        }
        for entry in entries
    ]
    history = (
        await db.execute(
            select(CopilotMessage)
            .where(
                CopilotMessage.copilot_session_id == session_id,
                CopilotMessage.tenant_id == principal.tenant_id,
            )
            .order_by(CopilotMessage.created_at.desc())
            .limit(7)
        )
    ).scalars().all()
    history.reverse()
    mutation_requested = attempts_business_mutation(masked_question)
    provider = "GEMINI"
    model_version: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    answer: str
    selected_citations = citations
    selected_actions: list[dict[str, str]] = []
    try:
        result = await call_llm(
            (
                "Act only as the NeuroX application copilot. Answer from the "
                "provided versioned help excerpts and live, authorization-filtered "
                "status. Never claim to perform a workflow mutation. Never expose "
                "private chain-of-thought. Use concise procedural steps and reason "
                "codes. Citation IDs and requested action IDs must come only from "
                "the supplied allowlists."
            ),
            {
                "_data_classification": settings.LLM_DATA_CLASSIFICATION,
                "question": masked_question,
                "current_screen": _screen_key(request.current_path),
                "roles": sorted(principal.roles),
                "mutation_requested": mutation_requested,
                "live_context": await _case_context(
                    db,
                    principal,
                    context_case_id,
                ),
                "conversation": [
                    {
                        "role": message.role,
                        "content": message.content_masked[:800],
                    }
                    for message in history
                ],
                "help_pack_version": HELP_PACK_VERSION,
                "help_excerpts": [
                    {
                        "source_id": entry.source_id,
                        "title": entry.title,
                        "content": entry.content,
                    }
                    for entry in entries
                ],
                "allowed_action_ids": sorted(action_registry),
                "available_ui_targets": [
                    target.model_dump()
                    for target in request.assistance_targets
                ],
            },
            CopilotDraft,
        )
        draft = result.output
        citation_ids = {
            citation["source_id"] for citation in citations
        }
        if any(
            citation_id not in citation_ids
            for citation_id in draft.citation_ids
        ) or any(
            action_id not in action_registry
            for action_id in draft.requested_action_ids
        ):
            raise LLMProviderError("LLM_OUTPUT_INVALID", retryable=True)
        answer = draft.answer
        if mutation_requested:
            answer = (
                "I cannot perform or bypass that controlled action. "
                + answer
            )
        selected_citations = [
            citation
            for citation in citations
            if citation["source_id"] in draft.citation_ids
        ] or citations[:2]
        selected_actions = [
            {
                "action_type": action_registry[action_id].action_type,
                "target": action_registry[action_id].target,
                "label": action_registry[action_id].label,
            }
            for action_id in draft.requested_action_ids
        ]
        model_version = result.model_version
        latency_ms = result.latency_ms
    except (LLMProviderError, ValueError) as exc:
        provider = "CAG_FALLBACK"
        error_code = (
            exc.error_code
            if isinstance(exc, LLMProviderError)
            else "LLM_PAYLOAD_REJECTED"
        )
        answer = _fallback_answer(
            entries,
            mutation_requested=mutation_requested,
        )
        selected_actions = [
            {
                "action_type": action.action_type,
                "target": action.target,
                "label": action.label,
            }
            for action in list(action_registry.values())[:2]
        ]

    assistant_message = CopilotMessage(
        tenant_id=principal.tenant_id,
        copilot_session_id=session.copilot_session_id,
        role="ASSISTANT",
        content_masked=mask_sensitive_text(answer),
        citations=selected_citations,
        ui_actions=selected_actions,
        provider=provider,
        model_version=model_version,
        latency_ms=latency_ms,
        error_code=error_code,
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(UTC)
    await db.flush()
    db.add(
        IdempotencyRecord(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            resource_id=assistant_message.copilot_message_id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=context_case_id,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="COPILOT_MESSAGE_CREATED",
        resource_type="COPILOT_SESSION",
        resource_id=str(session.copilot_session_id),
        metadata={
            "help_pack_version": HELP_PACK_VERSION,
            "provider": provider,
            "error_code": error_code,
            "citation_ids": [
                citation["source_id"]
                for citation in selected_citations
            ],
            "action_types": [
                action["action_type"] for action in selected_actions
            ],
        },
    )
    return _response(assistant_message)


@router.post(
    "/messages/{message_id}/feedback",
    response_model=CopilotFeedbackResponse,
    status_code=201,
)
async def create_feedback(
    message_id: uuid.UUID,
    request: CopilotFeedbackRequest,
    db: Db,
    principal: CurrentPrincipal,
    idempotency_key: IdempotencyKey,
):
    principal.require_any(*CASE_READ_ROLES)
    message = await db.scalar(
        select(CopilotMessage)
        .join(
            CopilotSession,
            CopilotSession.copilot_session_id
            == CopilotMessage.copilot_session_id,
        )
        .where(
            CopilotMessage.copilot_message_id == message_id,
            CopilotMessage.tenant_id == principal.tenant_id,
            CopilotMessage.role == "ASSISTANT",
            CopilotSession.user_id == principal.user_id,
        )
    )
    if not message:
        raise HTTPException(
            404,
            detail={"code": "COPILOT_MESSAGE_NOT_FOUND"},
        )
    existing_feedback = await db.scalar(
        select(CopilotFeedback).where(
            CopilotFeedback.copilot_message_id == message_id,
            CopilotFeedback.user_id == principal.user_id,
            CopilotFeedback.tenant_id == principal.tenant_id,
        )
    )
    if existing_feedback:
        if (
            existing_feedback.rating != request.rating
            or existing_feedback.reason_masked != request.reason
        ):
            raise HTTPException(
                409,
                detail={"code": "COPILOT_FEEDBACK_ALREADY_RECORDED"},
            )
        return existing_feedback
    scope = f"copilot.feedback:{principal.user_id}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = canonical_hash(
        {
            "message_id": str(message_id),
            **request.model_dump(mode="json"),
        }
    )
    existing_request = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == principal.tenant_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if existing_request:
        if existing_request.request_hash != request_hash:
            raise HTTPException(
                409,
                detail={"code": "IDEMPOTENCY_KEY_REUSED"},
            )
        replay = await db.get(
            CopilotFeedback,
            existing_request.resource_id,
        )
        if replay:
            return replay
    feedback = CopilotFeedback(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        copilot_message_id=message_id,
        rating=request.rating,
        reason_masked=request.reason,
        help_pack_version=HELP_PACK_VERSION,
    )
    db.add(feedback)
    await db.flush()
    db.add(
        IdempotencyRecord(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            resource_id=feedback.copilot_feedback_id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    await append_audit(
        db,
        tenant_id=principal.tenant_id,
        case_id=None,
        actor_type="USER",
        actor_id=str(principal.user_id),
        action="COPILOT_FEEDBACK_RECORDED",
        resource_type="COPILOT_MESSAGE",
        resource_id=str(message_id),
        metadata={
            "rating": request.rating,
            "help_pack_version": HELP_PACK_VERSION,
        },
    )
    return feedback


@router.get(
    "/feedback",
    response_model=list[CopilotFeedbackResponse],
)
async def list_feedback(
    db: Db,
    principal: CurrentPrincipal,
):
    principal.require_any("auditor", "admin")
    feedback = (
        await db.execute(
            select(CopilotFeedback)
            .where(
                CopilotFeedback.tenant_id == principal.tenant_id,
            )
            .order_by(CopilotFeedback.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    return list(feedback)
