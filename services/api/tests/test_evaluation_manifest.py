import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "evaluation" / "cases.jsonl"


def _records() -> list[dict]:
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_evaluation_manifest_is_reproducible_and_balanced():
    records = _records()
    assert len(records) == 100
    assert len({item["case_id"] for item in records}) == 100
    assert sum(
        item["workflow"] == "SUPPLIER_ONBOARDING" for item in records
    ) == 50
    assert sum(
        item["workflow"] == "INVOICE_EXCEPTION" for item in records
    ) == 50
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    expected = (
        ROOT / "evaluation" / "manifest.sha256"
    ).read_text(encoding="utf-8").split()[0]
    assert digest == expected


def test_evaluation_manifest_covers_mandatory_risk_scenarios():
    scenarios = {item["scenario"] for item in _records()}
    assert {
        "CLEAN_ONBOARDING",
        "CLEAN_THREE_WAY_MATCH",
        "DUPLICATE",
        "DUPLICATE_INVOICE",
        "SANCTIONS_CANDIDATE",
        "TAX_MISMATCH",
        "BANK_MISMATCH",
        "BANK_CHANGE",
        "MISSING_DOCUMENT",
        "MISSING_PO",
        "LOW_QUALITY_SCAN",
        "PROMPT_INJECTION",
        "RETRIEVAL_AMBIGUITY",
        "TRANSLITERATED_DUPLICATE",
        "CRITICAL_ID_CORRECTION",
    }.issubset(scenarios)
    assert all(item["synthetic_only"] for item in _records())
    assert all(item["requires_real_gemini"] for item in _records())
    assert all(item["resumable_on_quota"] for item in _records())


def test_every_referenced_document_exists_in_synthetic_corpus():
    for record in _records():
        assert record["documents"]
        for document in record["documents"]:
            path = ROOT / document
            assert path.is_file()
            assert str(path).startswith(
                str(ROOT / "Vendrai_Procurement_Document_Corpus_v2")
            )
