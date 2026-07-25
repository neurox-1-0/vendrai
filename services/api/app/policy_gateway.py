from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    deny_reasons: tuple[str, ...]


async def authorize_erp_write(
    policy_input: dict[str, Any],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PolicyDecision:
    try:
        async with httpx.AsyncClient(
            timeout=5,
            transport=transport,
        ) as client:
            response = await client.post(
                f"{settings.OPA_URL.rstrip('/')}/v1/data/neurox/erp/decision",
                json={"input": policy_input},
            )
            response.raise_for_status()
            result = response.json().get("result")
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("OPA_UNAVAILABLE") from exc
    if not isinstance(result, dict) or not isinstance(result.get("allow"), bool):
        raise RuntimeError("OPA_DECISION_INVALID")
    reasons = result.get("deny_reasons", [])
    if not isinstance(reasons, list) or not all(
        isinstance(reason, str) for reason in reasons
    ):
        raise RuntimeError("OPA_DECISION_INVALID")
    return PolicyDecision(
        allow=result["allow"],
        deny_reasons=tuple(sorted(set(reasons))),
    )
