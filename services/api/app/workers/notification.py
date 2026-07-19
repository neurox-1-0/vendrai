import asyncio
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select

from app.config import settings
from app.models import InboxReceipt, Notification, NotificationDelivery, User
from app.services.events import enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def send_email(destination: str, title: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = destination
    message["Subject"] = title
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as client:
        client.send_message(message)


async def deliver(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    notification_id = uuid.UUID(envelope["payload"]["notification_id"])
    attempt = int(envelope["payload"].get("attempt", 1))
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "notification-worker", "event_id": event_id}):
                return
            notification = await session.get(Notification, notification_id)
            if not notification or notification.tenant_id != tenant_id:
                raise RuntimeError("NOTIFICATION_NOT_FOUND")
            user_id = envelope["payload"].get("user_id")
            target_role = envelope["payload"].get("target_role")
            users = (await session.execute(select(User).where(User.tenant_id == tenant_id, User.status == "ACTIVE"))).scalars().all()
            recipients = [user for user in users if (user_id and str(user.user_id) == user_id) or (target_role and (target_role in user.roles or "admin" in user.roles))]
            if not recipients:
                notification.status = "DELIVERY_SKIPPED"
            for user in recipients:
                delivery = NotificationDelivery(
                    tenant_id=tenant_id, notification_id=notification_id, channel="EMAIL",
                    destination_masked=mask_email(user.email), attempts=attempt,
                )
                session.add(delivery)
                try:
                    await asyncio.to_thread(send_email, user.email, notification.title, notification.body)
                    delivery.status = "DELIVERED"
                    delivery.delivered_at = datetime.now(UTC)
                except Exception as exc:
                    delivery.status = "FAILED"
                    delivery.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                    if attempt < 5:
                        retry = enqueue_event(
                            session, tenant_id=tenant_id, aggregate_type="notification", aggregate_id=notification_id,
                            aggregate_version=attempt + 1, event_type="notification.delivery.requested.v1",
                            idempotency_key=f"notification.delivery:{notification_id}:{user.user_id}:{attempt + 1}",
                            payload={"notification_id": str(notification_id), "user_id": str(user.user_id), "attempt": attempt + 1},
                        )
                        retry.available_at = datetime.now(UTC) + timedelta(seconds=min(2 ** attempt * 15, 900))
            session.add(InboxReceipt(consumer_name="notification-worker", event_id=event_id, tenant_id=tenant_id))


if __name__ == "__main__":
    asyncio.run(consume("notification-worker", ["notification.delivery.requested.v1"], deliver))
