from pathlib import Path

from app.workers import document


def test_mixed_pdf_routes_only_image_page_to_ocr(monkeypatch):
    monkeypatch.setattr(document.settings, "DOCUMENT_PROCESSOR", "docling")
    monkeypatch.setattr(
        document,
        "extract_native_pdf",
        lambda _path: [
            (1, "A complete born-digital page with enough native text to use safely.", {"parser": "pypdf"}),
            (2, "", {"parser": "pypdf"}),
        ],
    )
    calls: list[bool] = []

    def fake_docling(_path, use_easyocr=False):
        calls.append(use_easyocr)
        return [
            (1, "OCR should not replace native page one", {"confidence": 0.9}),
            (2, "Scanned page two", {"confidence": 0.91}),
        ]

    monkeypatch.setattr(document, "extract_docling", fake_docling)
    pages, parser = document.extract_document(Path("mixed.pdf"), "application/pdf")
    assert pages[0][1].startswith("A complete born-digital")
    assert pages[0][2]["route"] == "native"
    assert pages[1][1] == "Scanned page two"
    assert pages[1][2]["route"] == "tesseract"
    assert calls == [False]
    assert parser == "docling-tesseract-easyocr"


def test_low_confidence_tesseract_page_uses_easyocr(monkeypatch):
    monkeypatch.setattr(document.settings, "DOCUMENT_PROCESSOR", "docling")
    monkeypatch.setattr(
        document,
        "extract_native_pdf",
        lambda _path: [(1, "", {"parser": "pypdf"})],
    )

    def fake_docling(_path, use_easyocr=False):
        if use_easyocr:
            return [(1, "Fallback text", {"confidence": 0.88})]
        return [(1, "Uncertain text", {"confidence": 0.20})]

    monkeypatch.setattr(document, "extract_docling", fake_docling)
    pages, _ = document.extract_document(Path("scan.pdf"), "application/pdf")
    assert pages[0][1] == "Fallback text"
    assert pages[0][2]["route"] == "easyocr-fallback"


def test_extraction_candidate_preserves_page_bbox_confidence_and_validation():
    candidates = document.extraction_candidates(
        [
            (
                2,
                "Account Number: 003-441-8821",
                {
                    "route": "tesseract",
                    "confidence": 0.82,
                    "items": [
                        {
                            "text": "003-441-8821",
                            "bbox": [10, 20, 100, 35],
                        }
                    ],
                },
            )
        ]
    )
    candidate = candidates["bank_account"]
    assert candidate["source_page"] == 2
    assert candidate["source_bbox"]["bbox"] == [10, 20, 100, 35]
    assert candidate["confidence"] == 0.82
    assert candidate["confidence_grade"] == "GOOD"
    assert all(item["passed"] for item in candidate["validation_results"])


def test_fields_stated_on_the_line_after_the_label_are_extracted():
    """The corpus puts label and value on separate lines; so do most forms."""
    candidates = document.extraction_candidates(
        [
            (
                1,
                "Legal name\nHarborline Logistics (Pvt) Ltd\n"
                "Beneficiary\nR. K. Jayawardena\n"
                "Bank country\nSri Lanka\n"
                "Email\nbilling@harborline-logistics.example\n",
                {"parser": "pypdf", "items": []},
            )
        ]
    )
    assert candidates["legal_name"]["raw"] == "Harborline Logistics (Pvt) Ltd"
    assert candidates["bank_beneficiary_name"]["raw"] == "R. K. Jayawardena"
    assert candidates["bank_country"]["raw"] == "Sri Lanka"
    assert candidates["email_domain"]["raw"] == "harborline-logistics.example"


def test_a_failed_validation_caps_confidence_below_the_unattended_threshold():
    candidates = document.extraction_candidates(
        [(1, "Tax ID\nX1\n", {"parser": "pypdf", "items": []})]
    )
    candidate = candidates["tax_id"]
    assert candidate["confidence"] < 0.60
    assert any(
        item["rule"] == "CRITICAL_IDENTIFIER_LENGTH" and not item["passed"]
        for item in candidate["validation_results"]
    )


def test_iban_checksum_rejects_a_transposed_digit():
    assert document.iban_checksum_valid("GB82 WEST 1234 5698 7654 32") is True
    assert document.iban_checksum_valid("GB82 WEST 1234 5698 7654 23") is False


def test_country_normalisation_reaches_the_stored_value():
    assert document.normalize_extracted_value("bank_country", "Hong Kong", False) == "HK"
    assert document.normalize_extracted_value("registered_country", "Sri Lanka", False) == "LK"
