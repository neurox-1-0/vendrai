import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.database import AsyncSessionLocal
from app.domain.analytics import CaseMetricRecord, summarize_metrics
from app.domain.fraud import isolation_forest_scores, robust_mad_score
from app.main import app
from app.models import Case, CaseEvent, InvoiceException, InvoiceRecord, RiskFinding
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from scripts.train_synthetic_anomaly_model import synthetic_history

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_event_derived_metric_formulas_and_robust_anomaly_fallback():
    submitted = datetime(2026, 7, 1, tzinfo=UTC)
    records = [
        CaseMetricRecord(
            case_id="clean",
            case_type="INVOICE_EXCEPTION",
            status="COMPLETED",
            submitted_at=submitted,
            terminal_at=submitted + timedelta(hours=4),
            human_touched=False,
            has_exception=False,
        ),
        CaseMetricRecord(
            case_id="reviewed",
            case_type="INVOICE_EXCEPTION",
            status="COMPLETED",
            submitted_at=submitted,
            terminal_at=submitted + timedelta(hours=8),
            human_touched=True,
            has_exception=True,
        ),
    ]
    metrics = summarize_metrics(
        records,
        open_approvals=3,
        period_end=submitted + timedelta(days=30),
    )
    assert metrics["invoice_stp_rate"]["value"] == 50
    assert metrics["invoice_cycle_hours"]["value"] == 6
    assert metrics["invoice_cycle_hours"]["statistics"]["p90"] == 7.6
    assert metrics["invoice_exception_rate"]["value"] == 50
    assert metrics["pending_approval_count"]["value"] == 3

    insufficient = robust_mad_score(100, [10, 11, 12])
    assert insufficient.anomalous is False
    anomaly = robust_mad_score(100, [10, 10, 11, 9, 10, 11])
    assert anomaly.anomalous is True
    training = synthetic_history(42, 1000)
    assert synthetic_history(42, 1000).tolist() == training.tolist()
    shadow_scores = isolation_forest_scores(
        training.tolist(),
        [[1.0, 1.0, 0.5, 10.0, 180.0, 0.0], [4.0, 5.0, 1.0, 0.0, 0.0, 5.0]],
    )
    assert len(shadow_scores) == 2
    assert shadow_scores[1] > shadow_scores[0]


@pytest.mark.asyncio
async def test_analytics_are_server_derived_and_requesters_cannot_read_aggregates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        draft = await client.post(
            "/api/v1/invoices:draft",
            json={"invoice_number": "AN-100", "currency": "LKR"},
            headers={"Idempotency-Key": "analytics-invoice-draft"},
        )
        assert draft.status_code == 201, draft.text
        case_id = uuid.UUID(draft.json()["case_id"])
        submitted = datetime.now(UTC) - timedelta(hours=6)
        async with AsyncSessionLocal() as session, session.begin():
            case = await session.get(Case, case_id)
            invoice = await session.scalar(
                select(InvoiceRecord).where(InvoiceRecord.case_id == case_id)
            )
            assert case and invoice
            case.status = "COMPLETED"
            case.submitted_at = submitted
            case.resolved_at = submitted + timedelta(hours=4)
            session.add(
                CaseEvent(
                    tenant_id=TENANT_ID,
                    case_id=case_id,
                    sequence=2,
                    event_type="CASE_SUBMITTED",
                    actor_type="USER",
                    actor_id="requester",
                    payload={},
                    created_at=submitted,
                )
            )
            session.add(
                CaseEvent(
                    tenant_id=TENANT_ID,
                    case_id=case_id,
                    sequence=3,
                    event_type="ERP_PROVIDER_CONFIRMED",
                    actor_type="SYSTEM",
                    actor_id="erp-worker",
                    payload={},
                    created_at=submitted + timedelta(hours=4),
                )
            )
            session.add(
                InvoiceException(
                    tenant_id=TENANT_ID,
                    case_id=case_id,
                    invoice_id=invoice.invoice_id,
                    exception_type="PRICE_VARIANCE",
                    severity="MEDIUM",
                    resolution_status="OPEN",
                )
            )
        summary = await client.get("/api/v1/analytics/summary")
        exception_breakdown = await client.get(
            "/api/v1/analytics/exceptions"
        )
        question = await client.post(
            "/api/v1/analytics/query",
            json={"question": "What is invoice STP this month?"},
            headers={"Idempotency-Key": "analytics-question-test"},
        )
        forbidden = await client.get(
            "/api/v1/analytics/summary",
            headers={"X-Dev-Roles": "requester"},
        )
    assert summary.status_code == 200, summary.text
    stp = next(
        item
        for item in summary.json()["metrics"]
        if item["key"] == "invoice_stp_rate"
    )
    assert stp["value"] == 100
    assert stp["numerator"] == 1
    assert exception_breakdown.json()["total"] == 1
    assert question.status_code == 200
    assert question.json()["provider"] == "GOVERNED_LOCAL"
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_risk_disposition_and_alert_evaluation_are_tenant_scoped_and_idempotent():
    finding_id = uuid.uuid4()
    async with AsyncSessionLocal() as session, session.begin():
        session.add(
            RiskFinding(
                risk_finding_id=finding_id,
                tenant_id=TENANT_ID,
                case_id=None,
                subject_type="VENDOR",
                subject_id="V-1",
                finding_type="BANK_ACCOUNT_CHANGE",
                severity="CRITICAL",
                mode="ACTIVE",
                detector_key="bank_blind_index_consistency",
                detector_version="1.0.0",
                score=1.0,
                threshold=1.0,
                reason_codes=["UNVERIFIED_BANK_ACCOUNT_CHANGE"],
            )
        )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        findings = await client.get("/api/v1/risk-findings")
        first_alerts = await client.post(
            "/api/v1/alerts:evaluate",
            headers={"Idempotency-Key": "evaluate-alerts-first"},
        )
        second_alerts = await client.post(
            "/api/v1/alerts:evaluate",
            headers={"Idempotency-Key": "evaluate-alerts-second"},
        )
        alerts = await client.get("/api/v1/alerts")
        disposition = await client.post(
            f"/api/v1/risk-findings/{finding_id}:disposition",
            json={
                "disposition": "CONFIRMED",
                "reason": "Verified independently by finance",
            },
            headers={"Idempotency-Key": "finding-disposition-test"},
        )
        hidden = await client.get(
            "/api/v1/risk-findings",
            headers={
                "X-Dev-Tenant-Id": (
                    "00000000-0000-0000-0000-000000000002"
                ),
                "X-Dev-User-Id": (
                    "00000000-0000-0000-0000-000000000202"
                ),
            },
        )
    assert findings.status_code == 200
    assert len(findings.json()) == 1
    assert first_alerts.status_code == 200, first_alerts.text
    assert second_alerts.status_code == 200
    assert len(alerts.json()) == 1
    assert alerts.json()[0]["risk_finding_id"] == str(finding_id)
    assert disposition.json()["status"] == "CLOSED"
    assert hidden.json() == []
