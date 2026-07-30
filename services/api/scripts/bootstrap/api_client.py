"""HTTP client that drives the product's own API as an administrator.

Bootstrapping through the API rather than the ORM is the point (see the package
docstring), which means the bootstrap needs a real admin principal. How it gets
one depends on the auth mode:

* ``development`` - the development headers the API already honours.
* ``keycloak``    - a direct-grant token for the ``admin`` realm user, using
  the same client the acceptance bootstrap provisions.

Both paths produce a principal the API authorises exactly as it would a human
administrator. Neither weakens a check for the bootstrap's benefit.
"""

from __future__ import annotations

import uuid
from types import TracebackType

import httpx
from app.config import settings


class BootstrapAuthError(RuntimeError):
    """The bootstrap could not obtain an administrator principal."""


class AdminApiClient:
    def __init__(self, tenant_id: uuid.UUID, *, base_url: str | None = None) -> None:
        self.tenant_id = tenant_id
        self.base_url = (base_url or settings.BOOTSTRAP_API_URL).rstrip("/")
        self.prefix = settings.API_PREFIX
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AdminApiClient:
        headers = await self._auth_headers()
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}{self.prefix}",
            headers=headers,
            timeout=60,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _auth_headers(self) -> dict[str, str]:
        if settings.AUTH_MODE == "development":
            return {
                "X-Dev-Tenant-Id": str(self.tenant_id),
                "X-Dev-User-Id": settings.DEV_USER_ID,
                "X-Dev-Roles": "admin",
            }
        return {"Authorization": f"Bearer {await self._keycloak_token()}"}

    async def _keycloak_token(self) -> str:
        token_url = f"{settings.KEYCLOAK_ISSUER}/protocol/openid-connect/token"
        if not settings.KEYCLOAK_E2E_CLIENT_SECRET or not settings.KEYCLOAK_E2E_USER_PASSWORD:
            raise BootstrapAuthError(
                "AUTH_MODE=keycloak but KEYCLOAK_E2E_CLIENT_SECRET or "
                "KEYCLOAK_E2E_USER_PASSWORD is unset, so the bootstrap cannot "
                "authenticate as an administrator. Run "
                "'docker compose --profile acceptance up keycloak-bootstrap' "
                "first, or set the values in .env."
            )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": "neurox-e2e",
                    "client_secret": settings.KEYCLOAK_E2E_CLIENT_SECRET,
                    "username": "admin",
                    "password": settings.KEYCLOAK_E2E_USER_PASSWORD,
                    "scope": "openid",
                },
            )
        if response.status_code != 200:
            raise BootstrapAuthError(
                f"Keycloak refused the administrator token request "
                f"({response.status_code}). Check that the realm was imported "
                "and the acceptance bootstrap has run."
            )
        return str(response.json()["access_token"])

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("AdminApiClient used outside its context manager")
        return self._client

    async def post(
        self,
        path: str,
        *,
        json: dict | None = None,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self.client.post(path, json=json, headers=headers)

    async def get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        return await self.client.get(path, params=params)

    async def wait_until_available(self, *, attempts: int = 30, delay: float = 2.0) -> None:
        """Block until the API answers, so ordering does not have to be exact."""
        import asyncio

        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                response = await httpx.AsyncClient(timeout=5).get(
                    f"{self.base_url}/health/ready"
                )
                if response.status_code == 200:
                    return
                last_error = RuntimeError(f"/health/ready returned {response.status_code}")
            except Exception as error:  # noqa: BLE001 - any failure is a retry
                last_error = error
            await asyncio.sleep(delay)
        raise BootstrapAuthError(
            f"The API at {self.base_url} never became ready ({last_error}). "
            "Check it with: ./scripts/stack.sh doctor"
        )
