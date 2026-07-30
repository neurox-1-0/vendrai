"""Document classification, the requirements matrix, and questionnaire reading."""

import pytest
from app.domain.documents import (
    DocumentType,
    classify_document,
    evaluate_completeness,
    extract_questionnaire_responses,
    questionnaire_controls,
)

ONBOARDING_FORM = """
HL
Harborline Logistics (Pvt) Ltd
Supplier onboarding record
Page 1
 SUPPLIER ONBOARDING FORM
Request reference: VON-2026-0720
1. Organisation details
"""

TAX_CERTIFICATE = """
DO
Department of Revenue Administration
Page 1
 TAX REGISTRATION CERTIFICATE
Certificate of registration for business tax purposes
"""

QUESTIONNAIRE = """
 SUPPLIER INFORMATION SECURITY
 QUESTIONNAIRE
Supplier: Nimbus Data Services Pte. Ltd.
#
Control question
Response
Details
1
Do you maintain an information security management
framework?
Yes
Internal control framework aligned to recognised
standards.
3
Will Asteria data be stored outside Sri Lanka?
Yes
Primary hosting in Singapore with disaster
recovery in Hong Kong.
5
Is a current data processing agreement available?
No
Commercial terms are under legal review.
Declaration
"""


def test_title_heading_classifies_a_document():
    document_type, signal = classify_document("01_form.pdf", ONBOARDING_FORM)
    assert document_type is DocumentType.SUPPLIER_ONBOARDING_FORM
    assert "title heading" in signal


def test_a_wrapped_title_heading_still_classifies():
    document_type, _ = classify_document("05_isq.pdf", QUESTIONNAIRE)
    assert document_type is DocumentType.INFOSEC_QUESTIONNAIRE


def test_filename_classifies_a_scan_whose_heading_did_not_survive():
    """VO-004 ships an onboarding form as a low-quality scan."""
    document_type, signal = classify_document(
        "01_supplier_onboarding_form_scan.pdf", "unreadable ocr output"
    )
    assert document_type is DocumentType.SUPPLIER_ONBOARDING_FORM
    assert "filename" in signal


def test_an_unrecognised_document_is_unknown_not_guessed():
    document_type, _ = classify_document("notes.pdf", "Some unrelated text.")
    assert document_type is DocumentType.UNKNOWN


def test_classification_reports_the_signal_that_decided_it():
    _, signal = classify_document("02_tax.pdf", TAX_CERTIFICATE)
    assert signal


def test_complete_submission_passes():
    """VO-001 ships all four always-required documents."""
    result = evaluate_completeness(
        {
            DocumentType.SUPPLIER_ONBOARDING_FORM,
            DocumentType.TAX_REGISTRATION,
            DocumentType.BANK_CONFIRMATION,
            DocumentType.INSURANCE_CERTIFICATE,
        },
        data_access_declared=False,
        data_stored_outside_country=False,
        spend_above_threshold=False,
    )
    assert result.disposition == "COMPLETE"
    assert result.missing == ()


def test_a_missing_always_required_document_is_named():
    """VO-003 deliberately omits the tax registration certificate."""
    result = evaluate_completeness(
        {
            DocumentType.SUPPLIER_ONBOARDING_FORM,
            DocumentType.BANK_CONFIRMATION,
            DocumentType.INSURANCE_CERTIFICATE,
            DocumentType.INFOSEC_QUESTIONNAIRE,
        },
        data_access_declared=True,
        data_stored_outside_country=True,
        spend_above_threshold=True,
    )
    assert result.disposition == "MISSING_REQUIRED"
    missing = {item.document_type for item in result.missing}
    assert DocumentType.TAX_REGISTRATION in missing
    assert result.reason_codes == ["MISSING_REQUIRED_DOCUMENT"]


def test_conditional_requirements_only_apply_when_their_condition_holds():
    base = {
        DocumentType.SUPPLIER_ONBOARDING_FORM,
        DocumentType.TAX_REGISTRATION,
        DocumentType.BANK_CONFIRMATION,
        DocumentType.INSURANCE_CERTIFICATE,
    }
    without = evaluate_completeness(
        base,
        data_access_declared=False,
        data_stored_outside_country=False,
        spend_above_threshold=False,
    )
    assert without.disposition == "COMPLETE"

    with_conditions = evaluate_completeness(
        base,
        data_access_declared=True,
        data_stored_outside_country=True,
        spend_above_threshold=True,
    )
    missing = {item.document_type for item in with_conditions.missing}
    assert missing == {
        DocumentType.INFOSEC_QUESTIONNAIRE,
        DocumentType.DATA_PROCESSING_AGREEMENT,
        DocumentType.BENEFICIAL_OWNERSHIP,
    }


def test_missing_documents_carry_the_reason_they_are_required():
    result = evaluate_completeness(
        set(),
        data_access_declared=False,
        data_stored_outside_country=False,
        spend_above_threshold=False,
    )
    assert all(item.reason for item in result.missing)
    assert all(item.label for item in result.missing)


def test_questionnaire_rows_parse_with_wrapped_questions_and_details():
    responses = extract_questionnaire_responses(QUESTIONNAIRE)
    assert [response.number for response in responses] == [1, 3, 5]
    assert responses[1].answer is True
    assert "Singapore" in responses[1].details


def test_questionnaire_controls_map_to_meaning_not_row_number():
    controls = questionnaire_controls(QUESTIONNAIRE)
    assert controls["data_stored_outside_country"].answer is True
    assert controls["data_processing_agreement_available"].answer is False


def test_an_unasked_control_is_absent_rather_than_false():
    """"We did not ask" and "they said no" are different findings."""
    controls = questionnaire_controls(
        "#\nControl question\nResponse\n1\nDo you have a firewall?\nYes\nManaged.\n"
    )
    assert "data_processing_agreement_available" not in controls


@pytest.mark.parametrize(
    "document_type",
    [
        DocumentType.SUPPLIER_ONBOARDING_FORM,
        DocumentType.TAX_REGISTRATION,
        DocumentType.BANK_CONFIRMATION,
        DocumentType.INSURANCE_CERTIFICATE,
    ],
)
def test_every_always_required_document_is_reported_when_absent(document_type):
    result = evaluate_completeness(
        set(),
        data_access_declared=False,
        data_stored_outside_country=False,
        spend_above_threshold=False,
    )
    assert document_type in {item.document_type for item in result.missing}
