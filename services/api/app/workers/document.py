import asyncio
import re
import socket
import struct
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.domain.cases import CaseStatus
from app.domain.pii import mask_sensitive_text
from app.domain.security import (
    blind_index,
    encrypt_sensitive_value,
    normalize_vendor_name,
)
from app.models import (
    AgentStep,
    Case,
    Document,
    DocumentPage,
    ExtractedField,
    InboxReceipt,
)
from app.services.events import append_case_event, enqueue_event
from app.services.risk import upsert_risk_finding
from app.services.storage import (
    copy_local_clean_object,
    delete_quarantined_object,
    document_key,
    local_object_path,
    materialize_object,
    promote_clean_object,
)
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from sqlalchemy import func, select

FIELD_PATTERNS = {
    "legal_name": re.compile(r"(?:legal\s+name|name)\s*[:\-]\s*([^\n]{2,160})", re.I),
    "tax_id": re.compile(r"(?:TIN|tax(?:payer)?\s*(?:identification)?\s*(?:number|id))\s*[:\-]\s*([A-Z0-9 -]{6,30})", re.I),
    "bank_account": re.compile(r"(?:account(?:\s+number)?|IBAN)\s*[:\-]\s*([A-Z0-9 -]{8,40})", re.I),
    "swift_code": re.compile(r"(?:SWIFT|BIC)(?:\s+code)?\s*[:\-]\s*([A-Z0-9]{8,11})", re.I),
    "address": re.compile(r"address\s*[:\-]\s*([^\n]{5,240})", re.I),
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")


def confidence_grade(confidence: float | None) -> str:
    if confidence is None:
        return "UNKNOWN"
    if confidence >= 0.90:
        return "EXCELLENT"
    if confidence >= 0.75:
        return "GOOD"
    if confidence >= 0.60:
        return "FAIR"
    return "POOR"


def extraction_candidate(
    pages: list[tuple[int, str, dict]],
    field_name: str,
    pattern: re.Pattern[str],
) -> dict[str, Any] | None:
    for page_number, text, layout in pages:
        match = pattern.search(text)
        if not match:
            continue
        raw = " ".join(match.group(1).split())
        source_bbox: dict[str, Any] = {}
        for item in layout.get("items", []):
            item_text = str(item.get("text", ""))
            if raw.lower() in item_text.lower() or item_text.lower() in raw.lower():
                source_bbox = {"bbox": item.get("bbox")}
                break
        route = str(layout.get("route") or layout.get("parser") or "unknown")
        route_confidence = layout.get("confidence")
        confidence = (
            float(route_confidence)
            if isinstance(route_confidence, (int, float))
            else 0.99
            if route == "native"
            else 0.85
        )
        validations = [{"rule": "NON_EMPTY", "passed": bool(raw)}]
        if field_name == "swift_code":
            validations.append(
                {
                    "rule": "SWIFT_LENGTH",
                    "passed": bool(re.fullmatch(r"[A-Z0-9]{8,11}", raw, re.I)),
                }
            )
        if field_name in {"tax_id", "bank_account"}:
            validations.append(
                {
                    "rule": "CRITICAL_IDENTIFIER_LENGTH",
                    "passed": 6 <= len(re.sub(r"\s+", "", raw)) <= 40,
                }
            )
        if not all(item["passed"] for item in validations):
            confidence = min(confidence, 0.59)
        return {
            "raw": raw,
            "source_page": page_number,
            "source_bbox": source_bbox,
            "confidence": round(confidence, 4),
            "confidence_grade": confidence_grade(confidence),
            "validation_results": validations,
            "extractor_version": "2.0.0",
        }
    return None


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
    if len(reader.pages) > settings.MAX_PDF_PAGES:
        raise RuntimeError("PDF_PAGE_LIMIT_EXCEEDED")
    pages = [(index + 1, page.extract_text() or "", {"parser": "pypdf", "items": []}) for index, page in enumerate(reader.pages)]
    return pages


def extract_docling(path: Path, use_easyocr: bool = False) -> list[tuple[int, str, dict]]:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            EasyOcrOptions,
            PdfPipelineOptions,
            TesseractCliOcrOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError("DOCLING_NOT_INSTALLED") from exc
    pipeline = PdfPipelineOptions()
    pipeline.do_ocr = True
    pipeline.do_table_structure = True
    pipeline.ocr_options = EasyOcrOptions(force_full_page_ocr=True) if use_easyocr else TesseractCliOcrOptions(force_full_page_ocr=True)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)})
    result = converter.convert(path)
    if len(result.document.pages) > settings.MAX_PDF_PAGES:
        raise RuntimeError("PDF_PAGE_LIMIT_EXCEEDED")
    page_items: dict[int, list[dict]] = {int(number): [] for number in result.document.pages}
    page_text: dict[int, list[str]] = {int(number): [] for number in result.document.pages}
    page_confidences: dict[int, list[float]] = {
        int(number): [] for number in result.document.pages
    }
    page_dimensions: dict[int, dict[str, float | None]] = {}
    for number, page in result.document.pages.items():
        size = getattr(page, "size", None)
        page_dimensions[int(number)] = {
            "width": float(size.width) if size and getattr(size, "width", None) else None,
            "height": float(size.height) if size and getattr(size, "height", None) else None,
        }
    for item, _level in result.document.iterate_items():
        text = getattr(item, "text", "") or ""
        confidence_value = getattr(item, "confidence", None)
        for provenance in getattr(item, "prov", []) or []:
            page_number = int(provenance.page_no)
            bbox = getattr(provenance, "bbox", None)
            locator = {
                "type": type(item).__name__,
                "bbox": bbox.as_tuple() if bbox and hasattr(bbox, "as_tuple") else None,
            }
            page_items.setdefault(page_number, []).append(locator)
            if isinstance(confidence_value, (int, float)):
                page_confidences.setdefault(page_number, []).append(
                    float(confidence_value)
                )
            if text.strip():
                page_text.setdefault(page_number, []).append(text.strip())
    return [
        (
            page_number,
            "\n".join(page_text.get(page_number, [])),
            {
                "parser": "docling",
                "ocr": "easyocr" if use_easyocr else "tesseract",
                "items": page_items.get(page_number, []),
                "dimensions": page_dimensions.get(page_number, {}),
                "confidence": (
                    sum(page_confidences.get(page_number, []))
                    / len(page_confidences[page_number])
                    if page_confidences.get(page_number)
                    else None
                ),
            },
        )
        for page_number in sorted(page_items)
    ]


def extract_image(path: Path) -> tuple[list[tuple[int, str, dict]], str]:
    import pytesseract
    from PIL import Image

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
        results = easyocr.Reader(["en"], gpu=False, model_storage_directory=settings.EASYOCR_MODEL_DIR, download_enabled=True).readtext(str(path))
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
        ocr_page_numbers = {
            page_number
            for page_number, text, _ in native
            if len(text.strip()) < settings.OCR_MIN_NATIVE_CHARACTERS
        }
        if native and not ocr_page_numbers:
            return native, "pypdf"
        if settings.DOCUMENT_PROCESSOR != "docling":
            raise RuntimeError("OCR_REQUIRED_DOCLING_WORKER")
        tesseract_pages = {
            page_number: (text, layout)
            for page_number, text, layout in extract_docling(path)
        }
        fallback_page_numbers = {
            page_number
            for page_number in ocr_page_numbers
            if page_number not in tesseract_pages
            or not tesseract_pages[page_number][0].strip()
            or (
                tesseract_pages[page_number][1].get("confidence") is not None
                and tesseract_pages[page_number][1]["confidence"]
                < settings.OCR_MIN_CONFIDENCE
            )
        }
        easyocr_pages: dict[int, tuple[str, dict]] = {}
        if fallback_page_numbers:
            easyocr_pages = {
                page_number: (text, layout)
                for page_number, text, layout in extract_docling(
                    path,
                    use_easyocr=True,
                )
            }
        pages = []
        for page_number, native_text, native_layout in native:
            if page_number not in ocr_page_numbers:
                pages.append(
                    (
                        page_number,
                        native_text,
                        {**native_layout, "route": "native"},
                    )
                )
                continue
            text, layout = (
                easyocr_pages.get(page_number, ("", {}))
                if page_number in fallback_page_numbers
                else tesseract_pages.get(page_number, ("", {}))
            )
            if not text.strip():
                raise RuntimeError(
                    f"NO_TEXT_EXTRACTED_PAGE_{page_number}"
                )
            pages.append(
                (
                    page_number,
                    text,
                    {
                        **layout,
                        "route": (
                            "easyocr-fallback"
                            if page_number in fallback_page_numbers
                            else "tesseract"
                        ),
                    },
                )
            )
        if not pages:
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
    return mask_sensitive_text(text)


def process_stored_document(
    document: Document,
    tenant_id: uuid.UUID,
) -> tuple[bool, str, list[tuple[int, str, dict[str, Any]]], str, str | None]:
    clean_key = document_key(str(tenant_id), str(document.document_id), document.mime_type)

    def process(source: Path) -> tuple[bool, str, list[tuple[int, str, dict[str, Any]]], str]:
        clean, scan_result = scan_with_clamav(source)
        if not clean:
            delete_quarantined_object(document.storage_key)
            return False, scan_result, [], ""
        pages, parser_version = extract_document(source, document.mime_type)
        if settings.STORAGE_BACKEND == "s3":
            promote_clean_object(document.storage_key, clean_key, source)
        else:
            copy_local_clean_object(source, clean_key)
        return True, scan_result, pages, parser_version

    if settings.STORAGE_BACKEND == "s3":
        with tempfile.TemporaryDirectory(prefix="neurox-document-") as temporary:
            source = Path(temporary) / str(document.document_id)
            materialize_object(settings.S3_QUARANTINE_BUCKET, document.storage_key, source)
            clean, scan_result, pages, parser_version = process(source)
    else:
        clean, scan_result, pages, parser_version = process(local_object_path(document.storage_key))
    return clean, scan_result, pages, parser_version, clean_key if clean else None


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
            processing_started_at = datetime.now(UTC)
            processing_started = time.perf_counter()
            clean, scan_result, pages, parser_version, clean_storage_key = await asyncio.to_thread(
                process_stored_document,
                document,
                tenant_id,
            )
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
            if not clean_storage_key:
                raise RuntimeError("CLEAN_STORAGE_KEY_MISSING")
            document.storage_key = clean_storage_key
            for page_number, text, layout in pages:
                session.add(DocumentPage(
                    tenant_id=tenant_id, document_id=document_id, page_number=page_number,
                    text_content=mask_page(text), layout_json={**layout, "pii_masked": True},
                    ocr_confidence=layout.get("confidence"),
                ))
            for field_name, pattern in FIELD_PATTERNS.items():
                candidate = extraction_candidate(pages, field_name, pattern)
                if not candidate:
                    continue
                raw = candidate["raw"]
                sensitive = field_name in {"tax_id", "bank_account", "swift_code", "address"}
                normalized = (
                    blind_index(raw, settings.BLIND_INDEX_SECRET).hex() if sensitive
                    else normalize_vendor_name(raw) if field_name == "legal_name" else raw.upper()
                )
                session.add(ExtractedField(
                    tenant_id=tenant_id, document_id=document_id, field_name=field_name,
                    field_value_masked=f"<{field_name.upper()}>" if sensitive else raw,
                    field_value_ciphertext=encrypt_sensitive_value(raw, settings.DATA_ENCRYPTION_SECRET) if sensitive else None,
                    normalized_value=normalized,
                    confidence=candidate["confidence"],
                    confidence_grade=candidate["confidence_grade"],
                    validation_results=candidate["validation_results"],
                    source_page=candidate["source_page"],
                    source_bbox=candidate["source_bbox"],
                    extractor_type="deterministic-regex",
                    extractor_version=candidate["extractor_version"],
                    human_verified=False,
                ))
                if (
                    field_name in {"tax_id", "bank_account"}
                    and candidate["confidence"] < 0.90
                ):
                    await upsert_risk_finding(
                        session,
                        tenant_id=tenant_id,
                        case_id=case.case_id,
                        subject_type="DOCUMENT",
                        subject_id=str(document_id),
                        finding_type="LOW_CONFIDENCE_EXTRACTION",
                        severity="HIGH",
                        mode="ACTIVE",
                        detector_key=f"critical_field_confidence:{field_name}",
                        detector_version="2.0.0",
                        score=1 - candidate["confidence"],
                        threshold=0.10,
                        reason_codes=["OCR_HUMAN_CONFIRMATION_REQUIRED"],
                        feature_snapshot={
                            "field_name": field_name,
                            "confidence": candidate["confidence"],
                            "confidence_grade": candidate[
                                "confidence_grade"
                            ],
                        },
                        explanation={
                            "summary": (
                                "A critical identifier did not reach the "
                                "unattended extraction confidence threshold."
                            )
                        },
                        evidence_refs=[
                            {
                                "source_type": "DOCUMENT_PAGE",
                                "document_id": str(document_id),
                                "page": candidate["source_page"],
                            }
                        ],
                    )
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
                if not run_id:
                    raise RuntimeError("AGENT_RUN_NOT_FOUND")
                processing_completed_at = datetime.now(UTC)
                session.add(
                    AgentStep(
                        tenant_id=tenant_id,
                        run_id=uuid.UUID(str(run_id)),
                        node_name="document_processing",
                        attempt=1,
                        status="SUCCESS",
                        input_summary={
                            "route_reason": (
                                "Uploaded evidence must be scanned, parsed, "
                                "masked, and validated locally."
                            ),
                            "dependencies": [],
                            "started_at": (
                                processing_started_at.isoformat()
                            ),
                        },
                        output_summary={
                            "document_id": str(document_id),
                            "page_count": len(pages),
                            "parser_version": parser_version,
                            "malware_status": document.malware_status,
                            "completed_at": (
                                processing_completed_at.isoformat()
                            ),
                        },
                        error={},
                        latency_ms=round(
                            (
                                time.perf_counter()
                                - processing_started
                            )
                            * 1000
                        ),
                    )
                )

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
