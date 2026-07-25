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
