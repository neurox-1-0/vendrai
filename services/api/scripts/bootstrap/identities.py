"""Provision the tenant and its role-separated users.

The old seed created four users, one of which held ``["auditor", "admin"]``.
A user with two roles cannot demonstrate segregation of duties: every approval
it performs is also an approval it could have granted itself, so no test using
it proves the control works.

These seven identities mirror exactly the Keycloak users the acceptance
bootstrap provisions, one role each, with ``external_subject`` set so the same
person resolves under ``AUTH_MODE=keycloak``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models import Tenant, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TENANT_NAME = "NeuroX Demo"
TENANT_SLUG = "neurox-demo"


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    username: str
    full_name: str
    role: str

    @property
    def email(self) -> str:
        # Matches infra/keycloak/bootstrap-acceptance.sh so the Keycloak user
        # and the database user are unmistakably the same person.
        return f"{self.username}@synthetic.neurox.local"


def _identity(suffix: int, username: str, full_name: str, role: str) -> Identity:
    return Identity(
        user_id=uuid.UUID(f"00000000-0000-0000-0000-0000000001{suffix:02d}"),
        username=username,
        full_name=full_name,
        role=role,
    )


# Deliberately one role each. Do not merge these, however convenient it looks
# during a demo - a combined identity silently removes the segregation of
# duties the product exists to demonstrate.
IDENTITIES: tuple[Identity, ...] = (
    _identity(1, "requester", "Demo Requester", "requester"),
    _identity(2, "analyst", "Demo Analyst", "analyst"),
    _identity(3, "procurement", "Demo Procurement Approver", "procurement_approver"),
    _identity(4, "compliance", "Demo Compliance Approver", "compliance_approver"),
    _identity(5, "finance", "Demo Finance Approver", "finance_approver"),
    _identity(6, "auditor", "Demo Auditor", "auditor"),
    _identity(7, "admin", "Demo Administrator", "admin"),
)


async def ensure_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        tenant = Tenant(tenant_id=tenant_id, name=TENANT_NAME, slug=TENANT_SLUG)
        session.add(tenant)
        await session.flush()
    return tenant


async def ensure_users(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Create or correct the seven identities. Returns how many exist after."""
    existing = {
        user.user_id: user
        for user in (
            await session.execute(select(User).where(User.tenant_id == tenant_id))
        ).scalars()
    }
    for identity in IDENTITIES:
        user = existing.get(identity.user_id)
        if user is None:
            session.add(
                User(
                    user_id=identity.user_id,
                    tenant_id=tenant_id,
                    external_subject=identity.username,
                    email=identity.email,
                    full_name=identity.full_name,
                    roles=[identity.role],
                )
            )
            continue
        # Re-running the bootstrap repairs a drifted role set. That is the
        # point of idempotency here: an identity that has acquired a second
        # role is a control failure, not a harmless difference.
        user.email = identity.email
        user.full_name = identity.full_name
        user.external_subject = identity.username
        user.roles = [identity.role]
    await session.flush()
    return len(IDENTITIES)


async def role_separation_holds(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    users = (
        await session.execute(select(User).where(User.tenant_id == tenant_id))
    ).scalars().all()
    provisioned = {user.user_id for user in users}
    if not {identity.user_id for identity in IDENTITIES}.issubset(provisioned):
        return False
    return all(
        len(user.roles or []) == 1
        for user in users
        if user.user_id in {identity.user_id for identity in IDENTITIES}
    )
