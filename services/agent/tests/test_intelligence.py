import pytest

from app.graph import InvestigationContext, run_investigation
from app.privacy import assert_llm_payload_safe, tokenize_sensitive_text
from app.schemas import ExtractedVendor, PolicyClause, SanctionsEntity, ToolStatus, VendorRecord
from app.tools.duplicate import find_duplicates
from app.tools.risk import screen_sanctions


def test_duplicate_score_is_deterministic_and_requires_review():
    incoming = ExtractedVendor(
        legal_name="Acme Technologies Ltd", normalized_legal_name="acme technologies",
        tax_id_token="tax-hash", bank_account_token="bank-hash", registered_country="US",
    )
    existing = VendorRecord(
        vendor_id="vendor-1", legal_name="Acme Technology LLC", normalized_legal_name="acme technology",
        tax_id_hash="tax-hash", bank_account_hash=None, registered_country="US",
    )
    result = find_duplicates(incoming, [existing], "dup-1")
    assert result.status == ToolStatus.SUCCESS
    assert result.data and result.data[0].score >= 0.70
    assert result.data[0].review_required


def test_sanctions_service_fails_closed_without_verified_data():
    result = screen_sanctions(ExtractedVendor(legal_name="Acme"), [], "risk-1")
    assert result.status == ToolStatus.BLOCKED
    assert result.data and result.data.disposition == "UNAVAILABLE"
    assert result.error_code == "SANCTIONS_DATA_UNAVAILABLE"


def test_pii_tokenizer_blocks_raw_sensitive_payloads():
    result = tokenize_sensitive_text("Email ap@acme.com and account 123456789012")
    assert "ap@acme.com" not in result.text
    assert "123456789012" not in result.text
    assert_llm_payload_safe(result.text)
    with pytest.raises(ValueError):
        assert_llm_payload_safe("send ap@acme.com")


@pytest.mark.asyncio
async def test_graph_builds_verified_packet_and_pauses_for_approval():
    context = InvestigationContext(
        vendors=[],
        sanctions_entities=[SanctionsEntity(
            source="OFAC", dataset_version="2026-07-19", entity_id="sdn-1",
            primary_name="Unrelated Entity", aliases=[], countries=["US"],
        )],
        policies=[PolicyClause(
            policy_id="PROC-101", version="1", clause_id="1", title="Vendor onboarding approval",
            content="New vendor onboarding requires bank details sanctions screening and human approval.",
            score=0, effective_date="2026-01-01",
        )],
    )
    state = await run_investigation({
        "case_id": "case-1", "run_id": "run-1", "tenant_id": "tenant-1", "case_version": 1,
        "extracted_vendor": ExtractedVendor(
            legal_name="Acme Services", normalized_legal_name="acme services", registered_country="US",
        ).model_dump(mode="json"),
        "events": [],
    }, context)
    assert state["verification"]["passed"] is True
    assert state["current_node"] == "approval_interrupt"
    assert state["evidence_packet"]["recommendation"] == "CREATE_VENDOR"
