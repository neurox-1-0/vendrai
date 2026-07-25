import pytest
from app.domain.pii import mask_sensitive_text, sensitive_entity_types
from app.llm_gateway import _classify_provider_error, validate_minimized_payload
from app.schemas import ApprovalDecisionRequest, FieldCorrectionRequest


class _InvalidKeyProviderError(Exception):
    code = 400
    status = "INVALID_ARGUMENT"
    message = "API key not valid. Please pass a valid API key."


@pytest.mark.parametrize(
    ("raw", "entity"),
    [
        ("contact invoices@example.test", "EMAIL_ADDRESS"),
        ("SWIFT ABCDLKLX", "SWIFT_CODE"),
        ("TIN: 123456789V", "TAX_ID"),
        ("Account Number: 001234567890", "BANK_ACCOUNT"),
        ("Registration No: PV123456", "COMPANY_REGISTRATION"),
        ("Call +94 77 123 4567", "PHONE_NUMBER"),
    ],
)
def test_custom_procurement_recognizers_mask_adversarial_values(
    raw,
    entity,
):
    assert entity in sensitive_entity_types(raw)
    masked = mask_sensitive_text(raw)
    assert raw != masked
    assert f"<{entity}>" in masked


def test_value_level_pii_guard_rejects_unmasked_value_under_safe_key():
    with pytest.raises(ValueError, match="LLM_PAYLOAD_REJECTED"):
        validate_minimized_payload(
            {
                "_data_classification": "SYNTHETIC",
                "notes": "Send to invoices@example.test",
            }
        )


def test_invalid_google_key_is_classified_as_auth_failure(monkeypatch):
    from app import llm_gateway

    monkeypatch.setattr(
        llm_gateway.errors,
        "APIError",
        _InvalidKeyProviderError,
    )
    classified = _classify_provider_error(_InvalidKeyProviderError())
    assert classified.error_code == "LLM_AUTH_INVALID"
    assert classified.retryable is False


def test_human_narratives_are_masked_and_payload_edits_rejected():
    decision = ApprovalDecisionRequest(
        decision="REJECTED",
        expected_version=2,
        evidence_hash="a" * 64,
        comment="Bank account 001234567890 must be corrected",
    )
    assert "001234567890" not in decision.comment
    correction = FieldCorrectionRequest(
        value="001234567890",
        expected_version=2,
        reason="Account Number: 001234567890 was mistyped",
    )
    assert correction.value == "001234567890"
    assert "001234567890" not in correction.reason
    with pytest.raises(ValueError, match="reanalysis"):
        ApprovalDecisionRequest(
            decision="APPROVED",
            expected_version=2,
            evidence_hash="a" * 64,
            edited_payload={"bank_account": "001234567890"},
        )
