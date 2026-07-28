from __future__ import annotations

import uuid
from typing import Any

from app.models import RiskFinding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_risk_finding(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    case_id: uuid.UUID | None,
    subject_type: str,
    subject_id: str | None,
    finding_type: str,
    severity: str,
    mode: str,
    detector_key: str,
    detector_version: str,
    score: float | None,
    threshold: float | None,
    reason_codes: list[str],
    feature_snapshot: dict[str, Any],
    explanation: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    data_origin: str = "PRODUCTION",
) -> RiskFinding:
    existing = await db.scalar(
        select(RiskFinding)
        .where(
            RiskFinding.tenant_id == tenant_id,
            RiskFinding.case_id == case_id,
            RiskFinding.finding_type == finding_type,
            RiskFinding.detector_key == detector_key,
            RiskFinding.status == "OPEN",
        )
        .order_by(RiskFinding.created_at.desc())
        .limit(1)
    )
    finding = existing or RiskFinding(
        tenant_id=tenant_id,
        case_id=case_id,
        subject_type=subject_type,
        subject_id=subject_id,
        finding_type=finding_type,
        detector_key=detector_key,
        detector_version=detector_version,
    )
    finding.severity = severity
    finding.mode = mode
    finding.data_origin = data_origin
    finding.score = score
    finding.threshold = threshold
    finding.reason_codes = reason_codes
    finding.feature_snapshot = feature_snapshot
    finding.explanation = explanation
    finding.evidence_refs = evidence_refs
    if not existing:
        db.add(finding)
    return finding
