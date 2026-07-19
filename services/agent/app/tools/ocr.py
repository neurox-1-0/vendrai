from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DocumentProcessingError(RuntimeError):
    pass


@dataclass
class ParsedPage:
    page_number: int
    text: str
    confidence: float | None = None
    layout: dict[str, Any] = field(default_factory=dict)


def extract_pages(path: Path, processor: str = "native") -> tuple[list[ParsedPage], str]:
    """Extract born-digital PDFs locally; Docling is required for OCR/layout mode."""
    if not path.exists():
        raise DocumentProcessingError("DOCUMENT_OBJECT_MISSING")
    if processor == "docling":
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise DocumentProcessingError("DOCLING_NOT_INSTALLED") from exc
        result = DocumentConverter().convert(path)
        document = result.document
        pages = []
        for page_no, page in document.pages.items():
            text = document.export_to_text(page_no=page_no)
            pages.append(ParsedPage(page_number=int(page_no), text=text, layout={"source": "docling"}))
        if not pages:
            raise DocumentProcessingError("NO_TEXT_EXTRACTED")
        return pages, "docling"
    if path.suffix.lower() != ".pdf" and path.read_bytes()[:5] != b"%PDF-":
        raise DocumentProcessingError("IMAGE_REQUIRES_DOCLING_OCR")
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise DocumentProcessingError("ENCRYPTED_PDF")
        pages = [ParsedPage(index + 1, page.extract_text() or "", layout={"source": "pypdf"}) for index, page in enumerate(reader.pages)]
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError("PDF_PARSE_FAILED") from exc
    if not any(page.text.strip() for page in pages):
        raise DocumentProcessingError("OCR_REQUIRED")
    return pages, "pypdf"
