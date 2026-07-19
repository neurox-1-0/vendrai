import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentPrincipal
from app.database import get_db
from app.models import Notification
from app.schemas import NotificationResponse


router = APIRouter(prefix="/notifications", tags=["notifications"])
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(db: Db, principal: CurrentPrincipal):
    return list((await db.execute(
        select(Notification).where(
            Notification.tenant_id == principal.tenant_id,
            (Notification.user_id == principal.user_id) | (Notification.user_id.is_(None)),
        ).order_by(Notification.created_at.desc()).limit(100)
    )).scalars().all())


@router.post("/{notification_id}:read", response_model=NotificationResponse)
async def mark_read(notification_id: uuid.UUID, db: Db, principal: CurrentPrincipal):
    notification = await db.scalar(select(Notification).where(
        Notification.notification_id == notification_id,
        Notification.tenant_id == principal.tenant_id,
        (Notification.user_id == principal.user_id) | (Notification.user_id.is_(None)),
    ).with_for_update())
    if not notification:
        raise HTTPException(404, detail={"code": "NOTIFICATION_NOT_FOUND"})
    notification.status = "READ"
    notification.read_at = datetime.now(UTC)
    return notification
