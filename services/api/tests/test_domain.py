import pytest

from app.domain.cases import CaseStatus, InvalidTransition, assert_transition
from app.domain.security import blind_index, canonical_hash, normalize_vendor_name
from app.services.storage import sanitize_filename, validate_upload_request


def test_case_state_machine_allows_only_declared_edges():
    assert_transition(CaseStatus.DRAFT, CaseStatus.SUBMITTED)
    with pytest.raises(InvalidTransition):
        assert_transition(CaseStatus.DRAFT, CaseStatus.COMPLETED)


def test_vendor_normalization_and_blind_index_are_deterministic():
    assert normalize_vendor_name("  Acmé Technologies (Pvt) Ltd. ") == "acme technologies"
    assert blind_index("98-7654321", "secret") == blind_index("98-7654321", "secret")
    assert blind_index("98-7654321", "secret") != blind_index("11-2233445", "secret")


def test_canonical_hash_ignores_mapping_order():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_upload_validation_rejects_dangerous_types():
    with pytest.raises(Exception):
        validate_upload_request("application/zip", 100)
    assert sanitize_filename("../../Tax Form 2026.pdf") == "Tax_Form_2026.pdf"
