import httpx
import pytest
from app.models import ApprovalTask, Case
from app.policy_gateway import authorize_erp_write
from app.workers.erp import _required_controls


@pytest.mark.asyncio
async def test_opa_erp_decision_is_typed_and_fail_closed():
    async def allowed(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/data/neurox/erp/decision"
        return httpx.Response(
            200,
            json={"result": {"allow": True, "deny_reasons": []}},
        )

    decision = await authorize_erp_write(
        {"tenant_id": "synthetic"},
        transport=httpx.MockTransport(allowed),
    )
    assert decision.allow is True
    assert decision.deny_reasons == ()

    async def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(RuntimeError, match="OPA_UNAVAILABLE"):
        await authorize_erp_write(
            {"tenant_id": "synthetic"},
            transport=httpx.MockTransport(unavailable),
        )


def test_required_erp_controls_are_derived_deterministically():
    supplier = Case(case_type="VENDOR_ONBOARDING")
    supplier_task = ApprovalTask(
        evidence_packet={
            "duplicate_candidates": [{"review_required": True}],
            "risk": {"disposition": "POSSIBLE_MATCH"},
        }
    )
    assert _required_controls(supplier, supplier_task) == {
        "DUPLICATE_REVIEW",
        "SANCTIONS_REVIEW",
    }

    invoice = Case(case_type="INVOICE_EXCEPTION")
    invoice_task = ApprovalTask(
        evidence_packet={
            "reason_codes": [
                "UNVERIFIED_BANK_ACCOUNT_CHANGE",
                "TAX_MISMATCH",
            ],
            "risk": {"duplicate_invoice_found": True},
            "exception": [{"exception_type": "TAX_MISMATCH"}],
        }
    )
    assert _required_controls(invoice, invoice_task) == {
        "DUPLICATE_REVIEW",
        "BANK_CHANGE_REVIEW",
        "TAX_REVIEW",
    }
