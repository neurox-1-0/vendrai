import asyncio
import re
import shutil
import socket
import struct
import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.domain.cases import CaseStatus
from app.domain.security import blind_index, encrypt_sensitive_value, normalize_vendor_name
from app.models import Case, Document, DocumentPage, ExtractedField, InboxReceipt
from app.services.events import append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant


FIELD_PATTERNS = {
    "legal_name": re.compile(r"(?:legal\s+name|name)\s*[:\-]\s*([^\n]{2,160})", re.I),
    "tax_id": re.compile(r"(?:TIN|tax(?:payer)?\s*(?:identification)?\s*(?:number|id))\s*[:\-]\s*([A-Z0-9 -]{6,30})", re.I),
    "bank_account": re.compile(r"(?:account(?:\s+number)?|IBAN)\s*[:\-]\s*([A-Z0-9 -]{8,40})", re.I),
    "swift_code": re.compile(r"(?:SWIFT|BIC)(?:\s+code)?\s*[:\-]\s*([A-Z0-9]{8,11})", re.I),
    "address": re.compile(r"address\s*[:\-]\s*([^\n]{5,240})", re.I),
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")


def scan_with_clamav(path: Path) -> tuple[bool, str]:
    try:
        with socket.create_connection((settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=30) as connection:
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(struct.pack("!I", 0))
            response = connection.recv(4096).decode(errors="replace")
        return response.rstrip("\0\n").endswith("OK"), response
    except OSError as exc:
        if settings.CLAMAV_REQUIRED:
            raise RuntimeError("CLAMAV_UNAVAILABLE") from exc
        return True, "CLAMAV_BYPASSED_DEVELOPMENT"


def extract_native_pdf(path: Path) -> list[tuple[int, str, dict]]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise RuntimeError("ENCRYPTED_PDF")
    pages = [(index + 1, page.extract_text() or "", {"parser": "pypdf", "items": []}) for index, page in enumerate(reader.pages)]
    return pages


def extract_docling(path: Path, use_easyocr: bool = False) -> list[tuple[int, str, dict]]:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions, TesseractCliOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("DOCLING_NOT_INSTALLED") from exc
    pipeline = PdfPipelineOptions()
    pipeline.do_ocr = True
    pipeline.do_table_structure = True
    pipeline.ocr_options = EasyOcrOptions(force_full_page_ocr=True) if use_easyocr else TesseractCliOcrOptions(force_full_page_ocr=True)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)})
    result = converter.convert(path)
    page_items: dict[int, list[dict]] = {int(number): [] for number in result.document.pages}
    page_text: dict[int, list[str]] = {int(number): [] for number in result.document.pages}
    for item, _level in result.document.iterate_items():
        text = getattr(item, "text", "") or ""
        for provenance in getattr(item, "prov", []) or []:
            page_number = int(provenance.page_no)
            bbox = getattr(provenance, "bbox", None)
            locator = {
                "type": type(item).__name__,
                "bbox": bbox.as_tuple() if bbox and hasattr(bbox, "as_tuple") else None,
            }
            page_items.setdefault(page_number, []).append(locator)
            if text.strip():
                page_text.setdefault(page_number, []).append(text.strip())
    return [
        (page_number, "\n".join(page_text.get(page_number, [])), {"parser": "docling", "ocr": "easyocr" if use_easyocr else "tesseract", "items": page_items.get(page_number, [])})
        for page_number in sorted(page_items)
    ]


def extract_image(path: Path) -> tuple[list[tuple[int, str, dict]], str]:
    from PIL import Image
    import pytesseract

    image = Image.open(path).convert("RGB")
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    items = []
    words = []
    confidences = []
    for index, word in enumerate(data.get("text", [])):
        word = word.strip()
        try:
            confidence = float(data["conf"][index]) / 100
        except (ValueError, TypeError):
            confidence = 0.0
        if not word:
            continue
        words.append(word)
        confidences.append(confidence)
        items.append({
            "type": "word", "text": word, "confidence": confidence,
            "bbox": [data["left"][index], data["top"][index], data["width"][index], data["height"][index]],
        })
    average = sum(confidences) / len(confidences) if confidences else 0.0
    if average >= 0.60 and words:
        return [(1, " ".join(words), {"parser": "tesseract", "confidence": average, "items": items})], "tesseract"
    try:
        import easyocr
        results = easyocr.Reader(["en"], gpu=False, model_storage_directory="/opt/easyocr", download_enabled=False).readtext(str(path))
    except Exception as exc:
        raise RuntimeError("LOW_CONFIDENCE_OCR_NO_FALLBACK_MODEL") from exc
    fallback_items = [{"type": "line", "bbox": bbox, "text": text, "confidence": confidence} for bbox, text, confidence in results]
    text = "\n".join(item["text"] for item in fallback_items)
    if not text.strip():
        raise RuntimeError("NO_TEXT_EXTRACTED")
    return [(1, text, {"parser": "easyocr", "items": fallback_items})], "easyocr"


def extract_document(path: Path, mime_type: str) -> tuple[list[tuple[int, str, dict]], str]:
    if mime_type == "application/pdf":
        native = extract_native_pdf(path)
        if native and all(text.strip() for _, text, _ in native):
            return native, "pypdf"
        if settings.DOCUMENT_PROCESSOR != "docling":
            raise RuntimeError("OCR_REQUIRED_DOCLING_WORKER")
        pages = extract_docling(path)
        if not all(text.strip() for _, text, _ in pages):
            pages = extract_docling(path, use_easyocr=True)
        if not any(text.strip() for _, text, _ in pages):
            raise RuntimeError("NO_TEXT_EXTRACTED")
        return pages, "docling-tesseract-easyocr"
    if settings.DOCUMENT_PROCESSOR != "docling":
        raise RuntimeError("IMAGE_REQUIRES_DOCLING_WORKER")
    return extract_image(path)


def mask_page(text: str) -> str:
    for pattern in (FIELD_PATTERNS["tax_id"], FIELD_PATTERNS["bank_account"], FIELD_PATTERNS["swift_code"], FIELD_PATTERNS["address"]):
        text = pattern.sub(lambda match: match.group(0).replace(match.group(1), "<SENSITIVE_VALUE>"), text)
    text = EMAIL_PATTERN.sub("<EMAIL_ADDRESS>", text)
    text = PHONE_PATTERN.sub("<PHONE_NUMBER>", text)
    return text


async def process_document_event(envelope: dict) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    document_id = uuid.UUID(envelope["payload"]["document_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "document-worker", "event_id": event_id}):
                return
            document = await session.scalar(select(Document).where(Document.document_id == document_id).with_for_update())
            if not document or document.tenant_id != tenant_id:
                raise RuntimeError("DOCUMENT_NOT_FOUND_OR_TENANT_MISMATCH")
            case = await session.scalar(select(Case).where(Case.case_id == document.case_id).with_for_update())
            case_was_draft = case.status == CaseStatus.DRAFT
            source = settings.LOCAL_STORAGE_ROOT.resolve() / "quarantine" / str(tenant_id) / str(document_id)
            clean, scan_result = await asyncio.to_thread(scan_with_clamav, source)
            if not clean:
                document.malware_status = "INFECTED"
                document.processing_status = "REJECTED"
                case.status = CaseStatus.FAILED
                await append_case_event(session, tenant_id=tenant_id, case_id=case.case_id, event_type="DOCUMENT_MALWARE_DETECTED", actor_type="SYSTEM", actor_id="document-worker", payload={"document_id": str(document_id)})
                session.add(InboxReceipt(consumer_name="document-worker", event_id=event_id, tenant_id=tenant_id))
                return
            document.malware_status = "CLEAN"
            document.processing_status = "PROCESSING"
            if not case_was_draft:
                case.status = CaseStatus.DOCUMENT_PROCESSING
            extension = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}.get(document.mime_type, "")
            destination = settings.LOCAL_STORAGE_ROOT.resolve() / "documents" / str(tenant_id) / f"{document_id}{extension}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            document.storage_key = f"documents/{tenant_id}/{document_id}{extension}"
            pages, parser_version = await asyncio.to_thread(extract_document, source, document.mime_type)
            combined = "\n".join(text for _, text, _ in pages)
            for page_number, text, layout in pages:
                session.add(DocumentPage(
                    tenant_id=tenant_id, document_id=document_id, page_number=page_number,
                    text_content=mask_page(text), layout_json={**layout, "pii_masked": True},
                ))
            for field_name, pattern in FIELD_PATTERNS.items():
                match = pattern.search(combined)
                if not match:
                    continue
                raw = " ".join(match.group(1).split())
                sensitive = field_name in {"tax_id", "bank_account", "swift_code", "address"}
                normalized = (
                    blind_index(raw, settings.BLIND_INDEX_SECRET).hex() if sensitive
                    else normalize_vendor_name(raw) if field_name == "legal_name" else raw.upper()
                )
                session.add(ExtractedField(
                    tenant_id=tenant_id, document_id=document_id, field_name=field_name,
                    field_value_masked=f"<{field_name.upper()}>" if sensitive else raw,
                    field_value_ciphertext=encrypt_sensitive_value(raw, settings.DATA_ENCRYPTION_SECRET) if sensitive else None,
                    normalized_value=normalized, confidence=0.95 if field_name in {"legal_name", "swift_code"} else 0.85,
                    source_page=1, source_bbox={}, extractor_type="deterministic-regex",
                    extractor_version="1.0.0", human_verified=False,
                ))
            shutil.move(source, destination)
            document.processing_status = "READY"
            document.parser_version = parser_version
            await append_case_event(session, tenant_id=tenant_id, case_id=case.case_id, event_type="DOCUMENT_READY", actor_type="SYSTEM", actor_id="document-worker", payload={"document_id": str(document_id), "pages": len(pages)})
            await session.flush()
            remaining = await session.scalar(select(func.count()).select_from(Document).where(Document.case_id == case.case_id, Document.processing_status != "READY"))
            if remaining == 0:
                if case_was_draft:
                    case.status = CaseStatus.DRAFT
                    await append_case_event(
                        session,
                        tenant_id=tenant_id,
                        case_id=case.case_id,
                        event_type="DRAFT_DOCUMENTS_READY",
                        actor_type="SYSTEM",
                        actor_id="document-worker",
                        payload={"document_id": str(document_id)},
                    )
                    session.add(InboxReceipt(consumer_name="document-worker", event_id=event_id, tenant_id=tenant_id))
                    return
                case.current_version += 1
                run_id = envelope["payload"].get("run_id")
                if not run_id:
                    from app.models import AgentRun
                    run_id = await session.scalar(select(AgentRun.run_id).where(AgentRun.case_id == case.case_id).order_by(AgentRun.created_at.desc()))
                
                if case.case_type == "INVOICE_EXCEPTION":
                    case.status = CaseStatus.INVOICE_MATCHING
                    enqueue_event(
                        session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case.case_id,
                        aggregate_version=case.current_version, event_type="invoice.analysis.requested.v1",
                        idempotency_key=f"invoice.analysis:{case.case_id}:v{case.current_version}",
                        payload={"case_id": str(case.case_id), "run_id": str(run_id)},
                    )
                else:
                    case.status = CaseStatus.SPECIALIST_ANALYSIS
                    enqueue_event(
                        session, tenant_id=tenant_id, aggregate_type="case", aggregate_id=case.case_id,
                        aggregate_version=case.current_version, event_type="agent.analysis.requested.v1",
                        idempotency_key=f"agent.analysis:{case.case_id}:v{case.current_version}",
                        payload={"case_id": str(case.case_id), "run_id": str(run_id)},
                    )
            session.add(InboxReceipt(consumer_name="document-worker", event_id=event_id, tenant_id=tenant_id))


if __name__ == "__main__":
    asyncio.run(consume("document-worker", ["document.processing.requested.v1"], process_document_event))
