from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, set_tenant_context
from app.models import Tenant, User


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID
    user_id: UUID
    subject: str
    email: str
    full_name: str
    roles: frozenset[str]

    def require_any(self, *roles: str) -> None:
        if not self.roles.intersection(roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "INSUFFICIENT_PERMISSION"})


@lru_cache
def jwks_client() -> PyJWKClient:
    url = settings.KEYCLOAK_JWKS_URL or f"{settings.KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
    return PyJWKClient(url, cache_keys=True)


def _roles_from_claims(claims: dict) -> frozenset[str]:
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    client_roles = claims.get("resource_access", {}).get(settings.KEYCLOAK_AUDIENCE, {}).get("roles", [])
    return frozenset(str(role) for role in [*realm_roles, *client_roles])


async def get_principal(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_dev_tenant_id: Annotated[str | None, Header()] = None,
    x_dev_user_id: Annotated[str | None, Header()] = None,
    x_dev_roles: Annotated[str | None, Header()] = None,
) -> Principal:
    if settings.AUTH_MODE == "development" and settings.APP_ENV != "production":
        tenant_id = UUID(x_dev_tenant_id or settings.DEV_TENANT_ID)
        user_id = UUID(x_dev_user_id or settings.DEV_USER_ID)
        roles = frozenset((x_dev_roles or "requester,analyst,approver,auditor,admin").split(","))
        principal = Principal(tenant_id, user_id, f"dev:{user_id}", "dev@neurox.local", "Development User", roles)
    else:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
        token = authorization.removeprefix("Bearer ").strip()
        try:
            signing_key = jwks_client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=settings.KEYCLOAK_AUDIENCE,
                issuer=settings.KEYCLOAK_ISSUER,
            )
            principal = Principal(
                tenant_id=UUID(claims["tenant_id"]),
                user_id=UUID(claims.get("user_id", claims["sub"])),
                subject=claims["sub"],
                email=claims.get("email", ""),
                full_name=claims.get("name", claims.get("preferred_username", "Unknown")),
                roles=_roles_from_claims(claims),
            )
        except (KeyError, ValueError, jwt.PyJWTError) as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN"}) from exc

    await set_tenant_context(db, str(principal.tenant_id))
    request.state.principal = principal
    if settings.AUTH_MODE == "development" and settings.APP_ENV != "production":
        await _ensure_development_identity(db, principal)
    return principal


async def _ensure_development_identity(db: AsyncSession, principal: Principal) -> None:
    tenant = await db.get(Tenant, principal.tenant_id)
    if not tenant:
        db.add(Tenant(
            tenant_id=principal.tenant_id,
            name="NeuroX Development",
            slug=f"neurox-dev-{str(principal.tenant_id)[-8:]}",
        ))
        await db.flush()
    user = await db.get(User, principal.user_id)
    if not user:
        db.add(User(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            external_subject=principal.subject,
            email=principal.email,
            full_name=principal.full_name,
            roles=sorted(principal.roles),
        ))
        await db.flush()


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
