"""Clarification questions and the policy query are derived, not templated."""

from app.domain.clarification import build_questions, for_control_finding
from app.domain.documents import (
    DocumentType,
    evaluate_completeness,
)
from app.domain.policy_query import build_supplier_policy_query


def _incomplete():
    return evaluate_completeness(
        {DocumentType.SUPPLIER_ONBOARDING_FORM, DocumentType.BANK_CONFIRMATION},
        data_access_declared=True,
        data_stored_outside_country=True,
        spend_above_threshold=False,
    )


def test_a_missing_document_question_names_the_document():
    questions = build_questions(completeness=_incomplete())
    text = " ".join(question.question for question in questions)
    assert "tax registration certificate" in text
    assert "insurance certificate" in text


def test_a_low_confidence_question_names_the_field_and_the_page():
    questions = build_questions(low_confidence_fields=[("tax_id", 1)])
    assert "tax id" in questions[0].question
    assert "page 1" in questions[0].question
    assert questions[0].locator == {"field": "tax_id", "page": 1}


def test_a_cross_border_question_names_both_countries():
    question = for_control_finding(
        "BANKING_COUNTRY_MISMATCH",
        {"bank_country": "HK", "registered_country": "SG"},
    )
    assert "HK" in question.question
    assert "SG" in question.question


def test_the_dpa_question_explains_why_it_is_needed():
    question = for_control_finding("DPA_UNAVAILABLE")
    assert "data processing agreement" in question.question.lower()
    assert "access company data" in question.question.lower()


def test_the_injection_question_states_the_instruction_was_not_acted_on():
    question = for_control_finding("UNTRUSTED_DOCUMENT_INSTRUCTION")
    assert "not been acted on" in question.question


def test_an_unknown_reason_code_produces_no_question_rather_than_a_bad_one():
    assert for_control_finding("SOMETHING_WE_HAVE_NOT_WRITTEN_YET") is None


def test_questions_are_deduplicated():
    questions = build_questions(
        control_reason_codes=["DPA_UNAVAILABLE", "DPA_UNAVAILABLE"],
    )
    assert len(questions) == 1


def test_missing_documents_come_before_control_questions():
    questions = build_questions(
        completeness=_incomplete(),
        control_reason_codes=["BANKING_COUNTRY_MISMATCH"],
    )
    reason_codes = [question.reason_code for question in questions]
    assert reason_codes.index("MISSING_REQUIRED_DOCUMENT") < reason_codes.index(
        "BANKING_COUNTRY_MISMATCH"
    )


def test_the_base_policy_query_always_covers_the_universal_clauses():
    query = build_supplier_policy_query()
    assert "supplier onboarding" in query.text
    assert "required documents" in query.text
    assert "human approval" in query.text


def test_findings_add_the_vocabulary_that_finds_their_clause():
    """VO-003 needs cross-border, residency, and insurance clauses.

    The fixed query it used to send contained none of those words, so
    retrieval could not cite what it never searched for.
    """
    query = build_supplier_policy_query(
        reason_codes=[
            "BANKING_COUNTRY_MISMATCH",
            "DATA_STORED_OUTSIDE_APPROVED_LOCATION",
            "CERTIFICATE_EXPIRED",
        ],
    )
    assert "cross-border banking" in query.text
    assert "data residency" in query.text
    assert "insurance" in query.text


def test_case_facts_contribute_even_without_a_finding():
    """A cross-border supplier is judged against the clause either way."""
    query = build_supplier_policy_query(
        registered_country="SG", bank_country="HK"
    )
    assert "cross-border supplier" in query.text


def test_the_query_records_which_findings_drove_it():
    query = build_supplier_policy_query(reason_codes=["DPA_UNAVAILABLE"])
    assert query.driven_by == ("DPA_UNAVAILABLE",)
    assert query.as_dict()["driven_by"] == ["DPA_UNAVAILABLE"]


def test_the_query_stays_bounded():
    query = build_supplier_policy_query(
        reason_codes=[
            "BANKING_COUNTRY_MISMATCH",
            "BANK_BENEFICIARY_MISMATCH",
            "DATA_STORED_OUTSIDE_APPROVED_LOCATION",
            "DPA_UNAVAILABLE",
            "CERTIFICATE_EXPIRED",
            "SPEND_ABOVE_ELEVATED_THRESHOLD",
            "MISSING_REQUIRED_DOCUMENT",
            "POSSIBLE_DUPLICATE",
            "SANCTIONS_REVIEW_REQUIRED",
            "ADVERSE_MEDIA_POSSIBLE_MATCH",
        ],
        registered_country="SG",
        bank_country="HK",
        data_access_declared=True,
        spend_elevated=True,
    )
    assert len(query.terms) <= 18
    assert len(query.terms) == len(set(query.terms))
