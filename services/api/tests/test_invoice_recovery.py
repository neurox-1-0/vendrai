import uuid
from decimal import Decimal

import pytest
from app.config import settings
from app.database import AsyncSessionLocal
from app.domain.cases import CaseStatus, InvalidTransition, assert_transition
from app.domain.security import canonical_hash
from app.main import app
from app.models import AgentRun, ApprovalTask, Case
from app.workers.invoice_agent import (
    _three_way_match,
    detect_document_type,
    extract_invoice_from_text,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.asyncio
async def test_invoice_draft_upload_and_submit_is_one_case():
    pdf = b"%PDF-1.4\n%%EOF\n"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        draft = await client.post(
            "/api/v1/invoices:draft",
            json={"invoice_number": "INV-100", "po_number": "PO-100", "currency": "LKR"},
            headers={"Idempotency-Key": "invoice-draft-100"},
        )
        duplicate_draft = await client.post(
            "/api/v1/invoices:draft",
            json={"invoice_number": "IGNORED"},
            headers={"Idempotency-Key": "invoice-draft-100"},
        )
        assert draft.status_code == 201, draft.text
        assert duplicate_draft.json()["case_id"] == draft.json()["case_id"]

        initiated = await client.post(
            f"/api/v1/cases/{draft.json()['case_id']}/documents:initiate",
            json={
                "filename": "invoice.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(pdf),
                "document_type": "INVOICE",
            },
            headers={"Idempotency-Key": "invoice-upload-100"},
        )
        assert initiated.status_code == 201, initiated.text
        upload = initiated.json()
        content = await client.put(
            upload["upload_url"],
            content=pdf,
            headers={"Content-Type": "application/pdf"},
        )
        assert content.status_code == 200, content.text
        completed = await client.post(
            f"/api/v1/documents/{upload['document_id']}:complete",
            headers={"Idempotency-Key": "invoice-complete-100"},
        )
        assert completed.status_code == 202, completed.text
        submitted = await client.post(
            f"/api/v1/cases/{draft.json()['case_id']}:submit",
            headers={"Idempotency-Key": "invoice-submit-100", "If-Match": "1"},
        )
        assert submitted.status_code == 202, submitted.text
        assert submitted.json()["case_id"] == draft.json()["case_id"]
        assert submitted.json()["run_id"]


@pytest.mark.asyncio
async def test_auditor_cannot_create_invoice_draft():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/invoices:draft",
            json={"invoice_number": "INV-REJECT"},
            headers={"Idempotency-Key": "invoice-auditor", "X-Dev-Roles": "auditor"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_escalation_preserves_safety_state_and_creates_admin_task():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        draft = await client.post(
            "/api/v1/invoices:draft",
            json={"invoice_number": "INV-ESCALATE"},
            headers={"Idempotency-Key": "invoice-escalation-draft"},
        )
        assert draft.status_code == 201, draft.text
        case_id = uuid.UUID(draft.json()["case_id"])
        run_id = uuid.uuid4()
        evidence_hash = canonical_hash({"case_id": str(case_id), "recommendation": "HOLD"})
        async with AsyncSessionLocal() as session:
            async with session.begin():
                case = await session.get(Case, case_id)
                assert case
                case.status = CaseStatus.APPROVAL_PENDING
                case.current_version = 2
                session.add(
                    AgentRun(
                        run_id=run_id,
                        tenant_id=case.tenant_id,
                        case_id=case_id,
                        thread_id=f"case:{case_id}:v2",
                        graph_name="invoice_exception",
                        status="INTERRUPTED",
                    )
                )
                task = ApprovalTask(
                    tenant_id=case.tenant_id,
                    case_id=case_id,
                    run_id=run_id,
                    task_type="INVOICE_AP_APPROVAL",
                    assigned_role="finance_approver",
                    proposed_action={"action": "RESOLVE_INVOICE_EXCEPTION"},
                    evidence_packet={"recommendation": "HOLD"},
                    evidence_hash=evidence_hash,
                    case_version=2,
                )
                session.add(task)
                await session.flush()
                task_id = task.approval_task_id

        response = await client.post(
            f"/api/v1/approval-tasks/{task_id}/decisions",
            json={
                "decision": "ESCALATED",
                "expected_version": 2,
                "evidence_hash": evidence_hash,
                "comment": "Independent senior review is required.",
            },
            headers={
                "Idempotency-Key": "invoice-escalation-decision",
                "If-Match": "2",
                "X-Dev-User-ID": str(uuid.uuid4()),
                "X-Dev-Roles": "admin",
            },
        )
        assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        case = await session.get(Case, case_id)
        escalated = await session.scalar(
            select(ApprovalTask).where(
                ApprovalTask.case_id == case_id,
                ApprovalTask.status == "PENDING",
                ApprovalTask.assigned_role == "admin",
            )
        )
        assert case
        assert case.status == CaseStatus.APPROVAL_PENDING
        assert case.current_version == 3
        assert escalated
        assert escalated.case_version == 3
        assert escalated.evidence_hash == evidence_hash
        assert str(settings.DEV_TENANT_ID) == str(escalated.tenant_id)


def test_invoice_extraction_fails_closed_without_critical_fields():
    extracted, missing = extract_invoice_from_text("TAX INVOICE\nInvoice No: INV-100\n")
    assert extracted is None
    assert {"total_amount", "currency", "line_items"}.issubset(missing)


def test_document_type_is_detected_from_local_text():
    assert detect_document_type("TAX INVOICE\nInvoice No: INV-100") == "INVOICE"
    assert detect_document_type("PURCHASE ORDER\nPO Number: PO-100") == "PURCHASE_ORDER"
    assert detect_document_type("GOODS RECEIPT\nGRN No: GRN-100") == "GOODS_RECEIPT"
    assert detect_document_type("untrusted arbitrary attachment") is None


def test_evidence_hash_is_canonical_non_placeholder_and_tamper_sensitive():
    packet = {
        "case_id": "case-1",
        "recommendation": "HOLD",
        "reason_codes": ["MISSING_ACCEPTED_GRN"],
    }
    evidence_hash = canonical_hash(packet)
    assert len(evidence_hash) == 64
    assert evidence_hash != "0" * 64
    assert evidence_hash == canonical_hash(dict(reversed(list(packet.items()))))
    assert evidence_hash != canonical_hash({**packet, "recommendation": "APPROVE_FOR_PAYMENT"})


def test_three_way_match_requires_grn_and_preserves_signed_variances():
    invoice = {
        "line_items": [
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": 8,
                "unit_price": 90,
                "amount": 720,
            }
        ]
    }
    result = _three_way_match(
        invoice,
        {
            "lines": {
                1: {
                    "line_number": 1,
                    "quantity": 10,
                    "unit_price": 100,
                    "amount": 1000,
                }
            }
        },
        {"lines": {}},
    )
    line = result["line_matches"][0]
    assert Decimal(str(line["price_variance"])) == Decimal("-10.0")
    assert Decimal(str(line["quantity_variance"])) == Decimal("8.0")
    assert line["match_status"] == "PARTIAL_MATCH"


def test_control_review_must_precede_separate_final_approval():
    assert_transition(
        CaseStatus.BLOCKED_DUPLICATE,
        CaseStatus.APPROVAL_PENDING,
    )
    assert_transition(CaseStatus.HOLD, CaseStatus.APPROVAL_PENDING)
    with pytest.raises(InvalidTransition):
        assert_transition(CaseStatus.BLOCKED_DUPLICATE, CaseStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        assert_transition(CaseStatus.HOLD, CaseStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        assert_transition(CaseStatus.BLOCKED_DUPLICATE, CaseStatus.COMPLETED)
