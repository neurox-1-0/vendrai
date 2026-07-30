"""Simulated third-party risk screening service.

The corpus README instructs evaluators to "configure the mock risk tool to
return values from mock_risk_api_results.json", and ships that file with
per-vendor sanctions, adverse-media, and country-risk verdicts. Nothing in the
product referenced it, so three stated expected findings were unreachable.

This is that service, built as a sibling of ``mock_erp``: same shape, same
Compose treatment, no new platform.

Two behaviours matter more than the happy path:

* An **unknown vendor** returns UNAVAILABLE, not CLEAR. A screening that did
  not happen is not a screening that passed.
* ``Crescent Stationery Traders`` is seeded with ``"sanctions": "UNAVAILABLE"``
  precisely so the fail-closed path gets exercised on a real case (VO-004).
  Do not "fix" that fixture.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="NeuroX Simulated Risk Screening", version="1.0.0")

RESULTS_PATH = Path(
    os.getenv("RISK_RESULTS_PATH", "/srv/risk/mock_risk_api_results.json")
)

# Set to make every lookup fail, so the outage path can be exercised on
# demand without stopping the container.
FORCE_UNAVAILABLE = os.getenv("RISK_FORCE_UNAVAILABLE", "").lower() in {
    "1",
    "true",
    "yes",
}

_LEGAL_SUFFIXES = re.compile(
    r"\b(llc|inc|incorporated|ltd|limited|plc|pvt|private|corp|corporation|"
    r"company|co|pte|sdn|bhd|gmbh|sarl|bv|nv|ag)\b",
    re.I,
)


def normalize(name: str) -> str:
    """Match the API's own vendor-name normalisation.

    Deliberately identical in behaviour to app.domain.security.normalize_vendor_name.
    Duplicated rather than imported because this service does not depend on the
    API package - the same reason mock_erp does not.
    """
    ascii_value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    without_suffixes = _LEGAL_SUFFIXES.sub(" ", ascii_value.lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_suffixes).split())


class RiskResult(BaseModel):
    legal_name: str
    matched_name: str | None
    sanctions: str
    adverse_media: str
    country_risk: str
    checked_at: str | None
    #: True when the provider has no record for this name. The caller must
    #: treat this as an unavailable check, not a clean one.
    unknown_vendor: bool = False


@lru_cache(maxsize=1)
def _seed() -> dict[str, dict[str, Any]]:
    if not RESULTS_PATH.exists():
        return {}
    raw = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {normalize(name): {"matched_name": name, **values} for name, values in raw.items()}


@app.get("/health")
def health() -> dict[str, Any]:
    seeded = _seed()
    return {
        "status": "healthy",
        "vendors_seeded": len(seeded),
        "force_unavailable": FORCE_UNAVAILABLE,
    }


@app.get("/v1/risk", response_model=RiskResult)
def screen(legal_name: str = Query(min_length=2, max_length=240)) -> RiskResult:
    if FORCE_UNAVAILABLE:
        raise HTTPException(503, detail={"code": "RISK_PROVIDER_UNAVAILABLE"})

    record = _seed().get(normalize(legal_name))
    if record is None:
        # An unrecognised supplier is not a clean supplier. Saying so is the
        # difference between a screening result and a shrug.
        return RiskResult(
            legal_name=legal_name,
            matched_name=None,
            sanctions="UNAVAILABLE",
            adverse_media="NOT RUN",
            country_risk="UNKNOWN",
            checked_at=datetime.now(UTC).isoformat(),
            unknown_vendor=True,
        )
    return RiskResult(
        legal_name=legal_name,
        matched_name=record.get("matched_name"),
        sanctions=str(record.get("sanctions", "UNAVAILABLE")),
        adverse_media=str(record.get("adverse_media", "NOT RUN")),
        country_risk=str(record.get("country_risk", "UNKNOWN")),
        checked_at=record.get("checked_at"),
        unknown_vendor=False,
    )
