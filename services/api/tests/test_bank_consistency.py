from app.domain.bank import (
    evaluate_bank_consistency,
    looks_like_individual,
    swift_country,
)


def test_matching_beneficiary_and_country_is_clear():
    result = evaluate_bank_consistency(
        legal_name="Northstar Office Systems (Pvt) Ltd",
        beneficiary_name="Northstar Office Systems (Pvt) Ltd",
        registered_country="LK",
        bank_country="LK",
    )
    assert result.disposition == "CLEAR"
    assert result.reason_codes == []


def test_legal_suffix_variation_still_matches():
    result = evaluate_bank_consistency(
        legal_name="Apex Digital Supplies (Pvt) Ltd",
        beneficiary_name="Apex Digital Supplies Private Limited",
        registered_country="LK",
        bank_country="LK",
    )
    assert result.disposition == "CLEAR"


def test_individual_beneficiary_is_a_mismatch_and_is_named_as_such():
    """VO-005: the beneficiary is a person, not the supplier entity."""
    result = evaluate_bank_consistency(
        legal_name="Harborline Logistics (Pvt) Ltd",
        beneficiary_name="R. K. Jayawardena",
        registered_country="LK",
        bank_country="LK",
    )
    assert result.disposition == "MISMATCH"
    assert "BANK_BENEFICIARY_MISMATCH" in result.reason_codes
    assert "BANK_BENEFICIARY_IS_INDIVIDUAL" in result.reason_codes
    assert result.requires_review is True


def test_cross_border_banking_is_a_mismatch():
    """VO-003: registered in Singapore, banking in Hong Kong."""
    result = evaluate_bank_consistency(
        legal_name="Nimbus Data Services Pte. Ltd.",
        beneficiary_name="Nimbus Data Services Pte. Ltd.",
        registered_country="SG",
        bank_country="HK",
    )
    assert result.disposition == "MISMATCH"
    assert result.reason_codes == ["BANKING_COUNTRY_MISMATCH"]
    assert result.signals["banking_country_mismatch"] is True


def test_absent_evidence_is_unverified_never_clear():
    result = evaluate_bank_consistency(
        legal_name="Acme Ltd",
        beneficiary_name=None,
        registered_country="LK",
        bank_country=None,
    )
    assert result.disposition == "UNVERIFIED"
    assert result.reason_codes == ["BANK_EVIDENCE_INCOMPLETE"]
    assert set(result.missing_evidence) == {"bank_beneficiary_name", "bank_country"}


def test_bank_country_falls_back_to_the_swift_code():
    result = evaluate_bank_consistency(
        legal_name="Acme Ltd",
        beneficiary_name="Acme Ltd",
        registered_country="SG",
        swift_code="HPBKHKHH",
    )
    assert result.signals["bank_country"] == "HK"
    assert result.signals["bank_country_source"] == "swift"
    assert result.disposition == "MISMATCH"


def test_declared_bank_country_wins_over_the_swift_code():
    result = evaluate_bank_consistency(
        legal_name="Acme Ltd",
        beneficiary_name="Acme Ltd",
        registered_country="LK",
        bank_country="LK",
        swift_code="HPBKHKHH",
    )
    assert result.signals["bank_country"] == "LK"
    assert result.signals["bank_country_source"] == "declared"
    assert result.disposition == "CLEAR"


def test_swift_country_extraction():
    assert swift_country("LMBKLKLX") == "LK"
    assert swift_country("HPBK HK HH") == "HK"
    assert swift_country("not-a-swift") is None
    assert swift_country(None) is None


def test_company_markers_prevent_an_individual_false_positive():
    assert looks_like_individual("R. K. Jayawardena") is True
    assert looks_like_individual("Mr Nimal Perera") is True
    assert looks_like_individual("Harborline Logistics (Pvt) Ltd") is False
    assert looks_like_individual("Crescent Stationery Traders") is False
