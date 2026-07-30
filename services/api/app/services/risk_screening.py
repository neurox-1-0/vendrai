"""Typed adapter over the third-party risk screening provider.

Distinct from sanctions screening: sanctions runs against official lists the
platform imports and stores, while this asks an external provider about adverse
media and country risk. Different data, different failure modes, different
finding.

The interpretation rules live in :func:`interpret` as a pure function, so the
judgement about what "POSSIBLE NAME MATCH - REVIEW" means is unit-testable
without a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import httpx
from app.config import settings

Disposition = Literal["CLEAR", "REVIEW_REQUIRED", "UNAVAILABLE"]

#: Provider verdicts that mean "we looked and found nothing".
_CLEAR_VERDICTS = frozenset({"CLEAR", "NO MATERIAL MATCH", "NO MATCH", "NONE"})
#: Verdicts that mean "we could not look". Never a pass.
_UNAVAILABLE_VERDICTS = frozenset(
    {"UNAVAILABLE", "NOT RUN", "ERROR", "UNKNOWN", "PENDING"}
)


@dataclass(frozen=True)
class RiskScreeningResult:
    disposition: Disposition
    sanctions: str | None = None
    adverse_media: str | None = None
    country_risk: str | None = None
    checked_at: str | None = None
    matched_name: str | None = None
    unknown_vendor: bool = False
    error_code: str | None = None
    reason_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "sanctions": self.sanctions,
            "adverse_media": self.adverse_media,
            "country_risk": self.country_risk,
            "checked_at": self.checked_at,
            "matched_name": self.matched_name,
            "unknown_vendor": self.unknown_vendor,
            "error_code": self.error_code,
            "reason_codes": self.reason_codes,
        }


def _verdict(value: str | None) -> str:
    return (value or "").strip().upper()


def interpret(payload: dict[str, object]) -> RiskScreeningResult:
    """Turn a provider response into a disposition and reason codes.

    The ordering matters: an unavailable signal outranks a clear one. A
    provider that could not run its sanctions check has not told us the
    supplier is clean, however cheerful the rest of the response looks.
    """
    sanctions = _verdict(str(payload.get("sanctions", "")))
    adverse_media = _verdict(str(payload.get("adverse_media", "")))
    country_risk = _verdict(str(payload.get("country_risk", "")))
    unknown_vendor = bool(payload.get("unknown_vendor"))

    reason_codes: list[str] = []
    unavailable = (
        unknown_vendor
        or sanctions in _UNAVAILABLE_VERDICTS
        or adverse_media in _UNAVAILABLE_VERDICTS
    )
    if unavailable:
        reason_codes.append("RISK_SERVICE_UNAVAILABLE")

    if adverse_media and adverse_media not in _CLEAR_VERDICTS | _UNAVAILABLE_VERDICTS:
        reason_codes.append("ADVERSE_MEDIA_POSSIBLE_MATCH")
    if sanctions and sanctions not in _CLEAR_VERDICTS | _UNAVAILABLE_VERDICTS:
        reason_codes.append("RISK_PROVIDER_SANCTIONS_MATCH")
    if country_risk in {"HIGH", "SEVERE"}:
        reason_codes.append("HIGH_COUNTRY_RISK")

    if unavailable:
        disposition: Disposition = "UNAVAILABLE"
    elif reason_codes:
        disposition = "REVIEW_REQUIRED"
    else:
        disposition = "CLEAR"

    return RiskScreeningResult(
        disposition=disposition,
        sanctions=str(payload.get("sanctions") or "") or None,
        adverse_media=str(payload.get("adverse_media") or "") or None,
        country_risk=str(payload.get("country_risk") or "") or None,
        checked_at=str(payload.get("checked_at") or "") or None,
        matched_name=str(payload.get("matched_name") or "") or None,
        unknown_vendor=unknown_vendor,
        reason_codes=reason_codes,
    )


def unavailable(error_code: str) -> RiskScreeningResult:
    return RiskScreeningResult(
        disposition="UNAVAILABLE",
        error_code=error_code,
        reason_codes=["RISK_SERVICE_UNAVAILABLE"],
    )


async def screen_vendor(legal_name: str) -> RiskScreeningResult:
    """Ask the provider about a supplier. Any failure is UNAVAILABLE.

    Failing closed is the whole point: an outage must be visible as a finding
    that routes to a human, not swallowed into a passing check.
    """
    if not legal_name.strip():
        return unavailable("RISK_SUBJECT_NAME_MISSING")
    try:
        async with httpx.AsyncClient(
            timeout=settings.RISK_SERVICE_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(
                f"{settings.RISK_SERVICE_URL}/v1/risk",
                params={"legal_name": legal_name},
            )
    except httpx.TimeoutException:
        return unavailable("RISK_SERVICE_TIMEOUT")
    except httpx.HTTPError:
        return unavailable("RISK_SERVICE_UNREACHABLE")
    if response.status_code != 200:
        return unavailable(f"RISK_SERVICE_HTTP_{response.status_code}")
    try:
        return interpret(response.json())
    except ValueError:
        return unavailable("RISK_SERVICE_MALFORMED_RESPONSE")
