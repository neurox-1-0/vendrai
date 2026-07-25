import asyncio
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from app.agents.workflow import tenant_workflow, workflow_config
from app.config import settings
from app.domain.cases import CaseStatus
from app.domain.security import canonical_hash, normalize_vendor_name
from app.models import (
    AgentRun,
    ApprovalTask,
    Case,
    ClarificationTask,
    Document,
    DocumentPage,
    EvidenceItem,
    ExtractedField,
    GoodsReceipt,
    GoodsReceiptLine,
    InboxReceipt,
    InvoiceException,
    InvoiceHistoryRecord,
    InvoiceLine,
    InvoiceRecord,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from app.services.events import append_audit, append_case_event, enqueue_event
from app.workers.common import consume
from app.workers.database import WorkerSession, set_worker_tenant
from sqlalchemy import delete, func, select

INVOICE_NUMBER = re.compile(
    r"(?:invoice\s+(?:number|no\.?|#)|tax\s+invoice\s+no|inv)[:\s]+([A-Z0-9][A-Z0-9./-]{2,})",
    re.IGNORECASE,
)
PO_NUMBER = re.compile(
    r"(?:po\s+(?:number|ref|#|no\.?)|purchase\s+order)[:\s]+([A-Z0-9][A-Z0-9./-]{2,})",
    re.IGNORECASE,
)
CURRENCY = re.compile(r"\b(USD|EUR|GBP|LKR|AUD|CAD|JPY|INR|SGD)\b", re.IGNORECASE)
TOTAL_AMOUNT = re.compile(
    r"(?:grand\s+total|amount\s+due|total\s+due|invoice\s+total|total)[:\s]+(?:[A-Z]{3}\s*)?([\d,]+(?:\.\d{1,4})?)",
    re.IGNORECASE,
)
TAX_AMOUNT = re.compile(
    r"(?:tax|vat)\s*(?:amount)?[:\s]+(?:[A-Z]{3}\s*)?([\d,]+(?:\.\d{1,4})?)",
    re.IGNORECASE,
)
TAX_RATE = re.compile(r"(?:vat|tax)\s*(?:rate)?[:\s]*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
LINE_PATTERN = re.compile(
    r"(?m)^\s*(\d+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(?:[A-Z]{3}\s*)?([\d,]+(?:\.\d{1,4})?)\s+(?:[A-Z]{3}\s*)?([\d,]+(?:\.\d{1,4})?)\s*$"
)
GRN_LINE_PATTERN = re.compile(
    r"(?m)^\s*(\d+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$"
)


def _decimal(value: str | int | float | Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("INVALID_MONETARY_VALUE") from exc


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def extract_invoice_from_text(text: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract only supported deterministic fields from locally masked page text."""
    invoice_number = _first_match(INVOICE_NUMBER, text)
    total_text = _first_match(TOTAL_AMOUNT, text)
    currency = (_first_match(CURRENCY, text) or "").upper()
    po_number = _first_match(PO_NUMBER, text)
    missing: list[str] = []
    if not invoice_number:
        missing.append("invoice_number")
    if not total_text:
        missing.append("total_amount")
    if not currency:
        missing.append("currency")

    line_items: list[dict[str, Any]] = []
    for match in LINE_PATTERN.finditer(text):
        line_number, description, quantity, unit_price, amount = match.groups()
        line_items.append(
            {
                "line_number": int(line_number),
                "description": " ".join(description.split())[:500],
                "quantity": float(_decimal(quantity)),
                "unit_price": _money(_decimal(unit_price)),
                "amount": _money(_decimal(amount)),
                "tax_rate": float(_decimal(_first_match(TAX_RATE, text) or "0")),
                "po_line_ref": line_number,
            }
        )
    if not line_items:
        missing.append("line_items")
    if missing:
        return None, missing

    vendor_name = next(
        (
            " ".join(line.split())[:240]
            for line in text.splitlines()[:10]
            if len(line.strip()) >= 3
            and not any(marker in line.upper() for marker in ("INVOICE", "PAGE ", "BILL TO", "SHIP TO"))
        ),
        None,
    )
    tax_text = _first_match(TAX_AMOUNT, text)
    return (
        {
            "invoice_number": invoice_number,
            "po_reference": po_number,
            "vendor_name": vendor_name,
            "total_amount": _money(_decimal(total_text)),
            "tax_amount": _money(_decimal(tax_text)),
            "tax_rate": float(_decimal(_first_match(TAX_RATE, text) or "0")),
            "currency": currency,
            "line_items": line_items,
        },
        [],
    )


def parse_po_text(text: str) -> dict[str, Any]:
    lines: dict[int, dict[str, Any]] = {}
    for match in LINE_PATTERN.finditer(text):
        line_number, description, quantity, unit_price, amount = match.groups()
        lines[int(line_number)] = {
            "line_number": int(line_number),
            "description": " ".join(description.split())[:500],
            "quantity": float(_decimal(quantity)),
            "unit_price": _money(_decimal(unit_price)),
            "amount": _money(_decimal(amount)),
        }
    return {
        "po_number": _first_match(PO_NUMBER, text),
        "tax_rate": float(_decimal(_first_match(TAX_RATE, text) or "0")),
        "lines": lines,
    }


def parse_grn_text(text: str) -> dict[str, Any]:
    lines: dict[int, dict[str, Any]] = {}
    for match in GRN_LINE_PATTERN.finditer(text):
        line_number, description, ordered, received = match.groups()
        lines[int(line_number)] = {
            "line_number": int(line_number),
            "description": " ".join(description.split())[:500],
            "ordered": float(_decimal(ordered)),
            "received": float(_decimal(received)),
        }
    return {"lines": lines}


def check_missing_po(extracted_invoice: dict[str, Any], all_case_docs: list[Any], po_data: dict[str, Any]) -> bool:
    """A printed PO reference is not proof; validated PO line data is mandatory."""
    del extracted_invoice, all_case_docs
    return not bool(po_data.get("lines"))


def check_tax_mismatch(extracted_invoice: dict[str, Any], po_data: dict[str, Any]) -> dict[str, Any]:
    invoice_rate = _decimal(extracted_invoice.get("tax_rate"))
    expected_rate = _decimal(po_data.get("tax_rate"))
    if expected_rate == 0:
        return {"mismatch": False, "unverified": True}
    if abs(invoice_rate - expected_rate) > Decimal("0.1"):
        return {
            "mismatch": True,
            "unverified": False,
            "invoice_tax_rate": float(invoice_rate),
            "expected_tax_rate": float(expected_rate),
            "message": (
                f"Tax mismatch detected: invoice rate {invoice_rate}% does not match the verified PO rate "
                f"{expected_rate}%."
            ),
        }
    return {"mismatch": False, "unverified": False}


async def _document_text(session, document_id: uuid.UUID) -> str:
    pages = (
        await session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        )
    ).scalars().all()
    return "\n".join(page.text_content or "" for page in pages)


async def _verified_invoice_corrections(
    session,
    document_id: uuid.UUID,
) -> str:
    fields = (
        await session.execute(
            select(ExtractedField).where(
                ExtractedField.document_id == document_id,
                ExtractedField.human_verified.is_(True),
                ExtractedField.field_name.in_(
                    {
                        "invoice_number",
                        "total_amount",
                        "currency",
                        "po_reference",
                        "po_number",
                    }
                ),
            )
        )
    ).scalars().all()
    labels = {
        "invoice_number": "INVOICE NUMBER",
        "total_amount": "INVOICE TOTAL",
        "currency": "CURRENCY",
        "po_reference": "PO NUMBER",
        "po_number": "PO NUMBER",
    }
    return "\n".join(
        f"{labels[field.field_name]}: {field.normalized_value}"
        for field in fields
        if field.normalized_value
    )


def detect_document_type(text: str) -> str | None:
    """Classify a supported AP document from locally extracted text."""
    upper = text.upper()
    if "GOODS RECEIPT" in upper or re.search(r"\bGRN(?:\s+NO|\s*#|[-:])", upper):
        return "GOODS_RECEIPT"
    if "PURCHASE ORDER" in upper:
        return "PURCHASE_ORDER"
    if "TAX INVOICE" in upper or re.search(r"\bINVOICE(?:\s+NO|\s*#|[-:])", upper):
        return "INVOICE"
    return None


async def _classify_documents(session, documents: list[Document]) -> dict[str, list[tuple[Document, str]]]:
    classified: dict[str, list[tuple[Document, str]]] = {
        "INVOICE": [],
        "PURCHASE_ORDER": [],
        "GOODS_RECEIPT": [],
    }
    for document in documents:
        text = await _document_text(session, document.document_id)
        declared = document.document_type.upper()
        detected = detect_document_type(text)
        if declared in classified:
            if detected != declared:
                continue
            kind = declared
        elif detected:
            kind = detected
        else:
            continue
        classified[kind].append((document, text))
    return classified


async def _reference_data(
    session,
    tenant_id: uuid.UUID,
    case: Case,
    invoice_record: InvoiceRecord,
    classified: dict[str, list[tuple[Document, str]]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    po_data: dict[str, Any] = {"po_number": invoice_record.po_number, "tax_rate": 0.0, "lines": {}}
    grn_data: dict[str, Any] = {"lines": {}}
    source = "NONE"
    if invoice_record.po_number:
        po = await session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.po_number == invoice_record.po_number,
            )
        )
        if po and (case.vendor_id is None or po.vendor_id == case.vendor_id):
            po_lines = (
                await session.execute(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.purchase_order_id == po.purchase_order_id
                    )
                )
            ).scalars().all()
            po_data = {
                "po_number": po.po_number,
                "tax_rate": float(po_lines[0].tax_rate) if po_lines else 0.0,
                "total_amount": float(po.total_amount),
                "lines": {
                    line.line_number: {
                        "line_number": line.line_number,
                        "description": line.item_description,
                        "quantity": float(line.quantity),
                        "unit_price": float(line.unit_price),
                        "amount": float(line.amount),
                    }
                    for line in po_lines
                },
            }
            receipts = (
                await session.execute(
                    select(GoodsReceipt).where(
                        GoodsReceipt.tenant_id == tenant_id,
                        GoodsReceipt.purchase_order_id == po.purchase_order_id,
                        GoodsReceipt.status == "RECEIVED",
                    )
                )
            ).scalars().all()
            for receipt in receipts:
                receipt_lines = (
                    await session.execute(
                        select(GoodsReceiptLine).where(
                            GoodsReceiptLine.goods_receipt_id == receipt.goods_receipt_id,
                            GoodsReceiptLine.quality_status == "ACCEPTED",
                        )
                    )
                ).scalars().all()
                for line in receipt_lines:
                    grn_data["lines"][line.line_number] = {
                        "line_number": line.line_number,
                        "received": float(line.quantity_received),
                    }
            source = "ERP_DATABASE"
    if not po_data["lines"] and classified["PURCHASE_ORDER"]:
        po_data = parse_po_text(classified["PURCHASE_ORDER"][0][1])
        source = "UPLOADED_DOCUMENT"
    if not grn_data["lines"] and classified["GOODS_RECEIPT"]:
        grn_data = parse_grn_text(classified["GOODS_RECEIPT"][0][1])
        source = f"{source}+UPLOADED_DOCUMENT"
    return po_data, grn_data, source


def _three_way_match(
    invoice: dict[str, Any],
    po_data: dict[str, Any],
    grn_data: dict[str, Any],
) -> dict[str, Any]:
    line_matches: list[dict[str, Any]] = []
    total_variance = Decimal("0")
    for item in invoice["line_items"]:
        line_number = int(item["line_number"])
        po_line = po_data.get("lines", {}).get(line_number)
        grn_line = grn_data.get("lines", {}).get(line_number)
        if not po_line:
            line_matches.append(
                {
                    "invoice_line": item,
                    "po_line": None,
                    "grn_line": grn_line,
                    "price_variance": 0.0,
                    "quantity_variance": 0.0,
                    "match_status": "MISSING_REFERENCE",
                }
            )
            continue
        invoice_price = _decimal(item["unit_price"])
        po_price = _decimal(po_line["unit_price"])
        invoice_quantity = _decimal(item["quantity"])
        received_quantity = _decimal(grn_line["received"]) if grn_line else Decimal("0")
        price_variance = invoice_price - po_price
        quantity_variance = invoice_quantity - received_quantity
        line_variance = abs(price_variance) * invoice_quantity + abs(quantity_variance) * po_price
        total_variance += line_variance
        line_matches.append(
            {
                "invoice_line": item,
                "po_line": po_line,
                "grn_line": grn_line,
                "price_variance": _money(price_variance),
                "quantity_variance": float(quantity_variance),
                "match_status": (
                    "FULL_MATCH"
                    if price_variance == 0 and quantity_variance == 0 and grn_line
                    else "PARTIAL_MATCH"
                ),
            }
        )
    po_total = sum((_decimal(line["amount"]) for line in po_data.get("lines", {}).values()), Decimal("0"))
    variance_pct = (total_variance / po_total * Decimal("100")) if po_total else Decimal("0")
    full = bool(line_matches) and all(item["match_status"] == "FULL_MATCH" for item in line_matches)
    return {
        "match_status": "FULL_MATCH" if full else "PARTIAL_MATCH",
        "line_matches": line_matches,
        "overall_variance_amount": _money(total_variance),
        "overall_variance_pct": float(variance_pct.quantize(Decimal("0.01"))),
    }


async def _policy_clauses(tenant_id: uuid.UUID, reason_codes: list[str]) -> list[dict[str, Any]]:
    query = (
        "Invoice exception approval, three-way matching, goods receipt, duplicate, bank change, "
        f"tax and tolerance controls. Reason codes: {', '.join(reason_codes)}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.RETRIEVAL_URL}/v1/search",
                json={
                    "query": query,
                    "tenant_id": str(tenant_id),
                    "roles": ["analyst", "finance_approver", "procurement_approver", "admin"],
                    "effective_date": date.today().isoformat(),
                    "limit": 8,
                },
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    if body.get("status") != "SUCCESS":
        return []
    return [
        {
            "policy_version_id": item.get("policy_version_id"),
            "clause_id": item.get("clause_id"),
            "heading_path": item.get("heading_path", []),
            "content": item.get("content", ""),
            "rerank_score": item.get("rerank_score"),
        }
        for item in body.get("items", [])
        if item.get("policy_version_id") and item.get("clause_id") and item.get("content")
    ]


async def _request_clarification(
    session,
    *,
    tenant_id: uuid.UUID,
    case: Case,
    run: AgentRun,
    questions: list[dict[str, Any]],
    reason_code: str,
) -> None:
    case.status = CaseStatus.NEEDS_CLARIFICATION
    case.current_version += 1
    run.status = "INTERRUPTED"
    run.current_node = "clarification_interrupt"
    run.state_json = {**run.state_json, "reason_code": reason_code}
    session.add(
        ClarificationTask(
            tenant_id=tenant_id,
            case_id=case.case_id,
            run_id=run.run_id,
            status="OPEN",
            questions=questions,
        )
    )
    await append_case_event(
        session,
        tenant_id=tenant_id,
        case_id=case.case_id,
        event_type="CLARIFICATION_REQUESTED",
        actor_type="SYSTEM",
        actor_id="invoice-worker",
        payload={"reason_code": reason_code},
    )


async def handle_invoice_submitted(envelope: dict[str, Any]) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "invoice-worker", "event_id": event_id}):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if not case or case.tenant_id != tenant_id or not run:
                raise RuntimeError("INVOICE_CONTEXT_NOT_FOUND")
            documents = (
                await session.execute(
                    select(Document).where(
                        Document.case_id == case_id,
                        Document.tenant_id == tenant_id,
                    )
                )
            ).scalars().all()
            if not documents:
                await _request_clarification(
                    session,
                    tenant_id=tenant_id,
                    case=case,
                    run=run,
                    reason_code="DOCUMENT_REQUIRED",
                    questions=[
                        {
                            "question_id": "invoice-document",
                            "text": "Upload an invoice document and resubmit the case.",
                            "field_name": "document",
                            "requested_from_role": "requester",
                        }
                    ],
                )
            elif all(document.processing_status == "READY" for document in documents):
                case.status = CaseStatus.INVOICE_MATCHING
                case.current_version += 1
                enqueue_event(
                    session,
                    tenant_id=tenant_id,
                    aggregate_type="case",
                    aggregate_id=case_id,
                    aggregate_version=case.current_version,
                    event_type="invoice.analysis.requested.v1",
                    idempotency_key=f"invoice.analysis:{case_id}:v{case.current_version}",
                    payload={"case_id": str(case_id), "run_id": str(run_id)},
                )
            else:
                await append_case_event(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    event_type="RUN_WAITING_FOR_DOCUMENTS",
                    actor_type="SYSTEM",
                    actor_id="invoice-worker",
                    payload={"run_id": str(run_id)},
                )
            session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))


async def run_invoice_analysis(envelope: dict[str, Any]) -> None:
    event_id = uuid.UUID(envelope["event_id"])
    tenant_id = uuid.UUID(envelope["tenant_id"])
    case_id = uuid.UUID(envelope["payload"]["case_id"])
    run_id = uuid.UUID(envelope["payload"]["run_id"])
    async with WorkerSession() as session:
        async with session.begin():
            await set_worker_tenant(session, str(tenant_id))
            if await session.get(InboxReceipt, {"consumer_name": "invoice-worker", "event_id": event_id}):
                return
            case = await session.get(Case, case_id, with_for_update=True)
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if not case or case.tenant_id != tenant_id or not run:
                raise RuntimeError("INVOICE_CONTEXT_NOT_FOUND")
            documents = (
                await session.execute(
                    select(Document).where(
                        Document.case_id == case_id,
                        Document.tenant_id == tenant_id,
                        Document.processing_status == "READY",
                    )
                )
            ).scalars().all()
            classified = await _classify_documents(session, documents)
            if len(classified["INVOICE"]) != 1:
                await _request_clarification(
                    session,
                    tenant_id=tenant_id,
                    case=case,
                    run=run,
                    reason_code="INVOICE_DOCUMENT_AMBIGUOUS",
                    questions=[
                        {
                            "question_id": "invoice-document",
                            "text": "Provide exactly one document classified as INVOICE.",
                            "field_name": "document_type",
                            "requested_from_role": "requester",
                        }
                    ],
                )
                session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))
                return

            invoice_document, invoice_text = classified["INVOICE"][0]
            verified_corrections = await _verified_invoice_corrections(
                session,
                invoice_document.document_id,
            )
            if verified_corrections:
                invoice_text = f"{invoice_text}\n{verified_corrections}"
            extracted_invoice, missing_fields = extract_invoice_from_text(invoice_text)
            if not extracted_invoice:
                await _request_clarification(
                    session,
                    tenant_id=tenant_id,
                    case=case,
                    run=run,
                    reason_code="INVOICE_EXTRACTION_INCOMPLETE",
                    questions=[
                        {
                            "question_id": field,
                            "text": f"Confirm or correct invoice field: {field}.",
                            "field_name": field,
                            "requested_from_role": "requester",
                        }
                        for field in missing_fields
                    ],
                )
                session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))
                return

            invoice_record = await session.scalar(
                select(InvoiceRecord).where(
                    InvoiceRecord.case_id == case_id,
                    InvoiceRecord.tenant_id == tenant_id,
                )
            )
            if not invoice_record:
                invoice_record = InvoiceRecord(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    vendor_id=case.vendor_id,
                    invoice_number=extracted_invoice["invoice_number"],
                    po_number=extracted_invoice.get("po_reference"),
                    total_amount=extracted_invoice["total_amount"],
                    tax_amount=extracted_invoice["tax_amount"],
                    currency=extracted_invoice["currency"],
                )
                session.add(invoice_record)
                await session.flush()
            invoice_record.invoice_number = extracted_invoice["invoice_number"]
            invoice_record.po_number = extracted_invoice.get("po_reference") or invoice_record.po_number
            invoice_record.total_amount = extracted_invoice["total_amount"]
            invoice_record.tax_amount = extracted_invoice["tax_amount"]
            invoice_record.currency = extracted_invoice["currency"]
            invoice_record.status = "ANALYZING"
            await session.execute(delete(InvoiceLine).where(InvoiceLine.invoice_id == invoice_record.invoice_id))
            await session.execute(delete(InvoiceException).where(InvoiceException.case_id == case_id))
            for item in extracted_invoice["line_items"]:
                session.add(
                    InvoiceLine(
                        tenant_id=tenant_id,
                        invoice_id=invoice_record.invoice_id,
                        line_number=item["line_number"],
                        description=item["description"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        amount=item["amount"],
                        tax_rate=item["tax_rate"],
                        po_line_ref=item["po_line_ref"],
                    )
                )

            po_data, grn_data, reference_source = await _reference_data(
                session, tenant_id, case, invoice_record, classified
            )
            match_result = _three_way_match(extracted_invoice, po_data, grn_data)
            reason_codes: list[str] = []
            exceptions: list[dict[str, Any]] = []
            missing_po = check_missing_po(extracted_invoice, documents, po_data)
            missing_grn = not bool(grn_data.get("lines"))
            if missing_po:
                reason_codes.append("MISSING_VERIFIED_PO")
            if missing_grn:
                reason_codes.append("MISSING_ACCEPTED_GRN")
            for line in match_result["line_matches"]:
                line_number = line["invoice_line"]["line_number"]
                if line["po_line"] is None:
                    exceptions.append(
                        {
                            "exception_type": "MISSING_PO_LINE",
                            "severity": "HIGH",
                            "confidence": 1.0,
                            "mismatch_details": {"line_number": line_number},
                            "affected_lines": [line_number],
                        }
                    )
                if line["price_variance"] != 0:
                    exceptions.append(
                        {
                            "exception_type": "PRICE_VARIANCE",
                            "severity": "MEDIUM",
                            "confidence": 1.0,
                            "mismatch_details": {
                                "line_number": line_number,
                                "variance": line["price_variance"],
                            },
                            "affected_lines": [line_number],
                        }
                    )
                if line["quantity_variance"] != 0:
                    exceptions.append(
                        {
                            "exception_type": "QUANTITY_VARIANCE",
                            "severity": "HIGH" if line["quantity_variance"] > 0 else "MEDIUM",
                            "confidence": 1.0,
                            "mismatch_details": {
                                "line_number": line_number,
                                "variance": line["quantity_variance"],
                            },
                            "affected_lines": [line_number],
                        }
                    )

            vendor = await session.get(Vendor, case.vendor_id) if case.vendor_id else None
            if not vendor and extracted_invoice.get("vendor_name"):
                normalized = normalize_vendor_name(extracted_invoice["vendor_name"])
                vendor = await session.scalar(
                    select(Vendor).where(
                        Vendor.tenant_id == tenant_id,
                        Vendor.normalized_legal_name == normalized,
                    )
                )
                if vendor:
                    case.vendor_id = vendor.vendor_id
                    invoice_record.vendor_id = vendor.vendor_id
            duplicate = False
            if vendor:
                duplicate = bool(
                    await session.scalar(
                        select(func.count())
                        .select_from(InvoiceHistoryRecord)
                        .where(
                            InvoiceHistoryRecord.tenant_id == tenant_id,
                            InvoiceHistoryRecord.vendor_id == str(vendor.vendor_id),
                            func.lower(InvoiceHistoryRecord.invoice_number)
                            == extracted_invoice["invoice_number"].lower(),
                        )
                    )
                )
            else:
                reason_codes.append("VENDOR_UNRESOLVED")
            if duplicate:
                reason_codes.append("DUPLICATE_INVOICE")
                exceptions.append(
                    {
                        "exception_type": "DUPLICATE_INVOICE",
                        "severity": "CRITICAL",
                        "confidence": 1.0,
                        "mismatch_details": {"invoice_number": extracted_invoice["invoice_number"]},
                        "affected_lines": [],
                    }
                )

            bank_field = await session.scalar(
                select(ExtractedField).where(
                    ExtractedField.document_id == invoice_document.document_id,
                    ExtractedField.field_name == "bank_account",
                )
            )
            bank_mismatch = False
            bank_unverified = False
            if bank_field:
                if vendor and vendor.bank_account_hash:
                    bank_mismatch = bank_field.normalized_value != vendor.bank_account_hash.hex()
                else:
                    bank_unverified = True
            if bank_mismatch:
                reason_codes.append("UNVERIFIED_BANK_ACCOUNT_CHANGE")
                exceptions.append(
                    {
                        "exception_type": "UNVERIFIED_BANK_ACCOUNT_CHANGE",
                        "severity": "CRITICAL",
                        "confidence": 1.0,
                        "mismatch_details": {"message": "Invoice bank blind index differs from vendor master."},
                        "affected_lines": [],
                    }
                )
            elif bank_unverified:
                reason_codes.append("BANK_ACCOUNT_UNVERIFIED")

            tax_result = check_tax_mismatch(extracted_invoice, po_data)
            if tax_result["mismatch"]:
                reason_codes.append("TAX_MISMATCH")
                exceptions.append(
                    {
                        "exception_type": "TAX_MISMATCH",
                        "severity": "HIGH",
                        "confidence": 1.0,
                        "mismatch_details": {"message": tax_result["message"]},
                        "affected_lines": [],
                    }
                )
            elif tax_result.get("unverified"):
                reason_codes.append("TAX_POLICY_UNVERIFIED")

            threshold_amount = Decimal("50.00")
            threshold_pct = Decimal("5.00")
            variance_amount = _decimal(match_result["overall_variance_amount"])
            variance_pct = _decimal(match_result["overall_variance_pct"])
            within_tolerance = (
                abs(variance_amount) <= threshold_amount
                and abs(variance_pct) <= threshold_pct
                and not missing_po
                and not missing_grn
            )
            if not within_tolerance:
                reason_codes.append("EXCEEDS_TOLERANCE")
            reason_codes = sorted(set(reason_codes or ["CLEAN_THREE_WAY_MATCH"]))
            policies = await _policy_clauses(tenant_id, reason_codes)
            if not policies:
                case.status = CaseStatus.VERIFICATION_FAILED
                case.current_version += 1
                run.status = "BLOCKED"
                run.current_node = "policy_evidence_unavailable"
                run.state_json = {
                    **run.state_json,
                    "reason_code": "INSUFFICIENT_POLICY_EVIDENCE",
                }
                await append_case_event(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    event_type="VERIFICATION_FAILED",
                    actor_type="SYSTEM",
                    actor_id="invoice-worker",
                    payload={"reason_code": "INSUFFICIENT_POLICY_EVIDENCE"},
                )
                session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))
                return

            tolerance = {
                "within_tolerance": within_tolerance,
                "threshold_amount": float(threshold_amount),
                "threshold_pct": float(threshold_pct),
                "actual_variance": float(variance_amount),
                "policy_ref": [
                    {"policy_version_id": item["policy_version_id"], "clause_id": item["clause_id"]}
                    for item in policies
                ],
            }
            recommendation = (
                "BLOCK_DUPLICATE"
                if duplicate
                else "HOLD"
                if bank_mismatch or missing_grn
                else "REQUEST_INFORMATION"
                if missing_po or not vendor
                else "REVIEW_REQUIRED"
                if exceptions or not within_tolerance
                else "APPROVE_FOR_PAYMENT"
            )
            packet = {
                "case_id": str(case_id),
                "run_id": str(run_id),
                "recommendation": recommendation,
                "reason_codes": reason_codes,
                "extracted_invoice": extracted_invoice,
                "match_result": match_result,
                "exception": exceptions,
                "tolerance": tolerance,
                "risk": {
                    "disposition": "REQUIRES_REVIEW" if reason_codes != ["CLEAN_THREE_WAY_MATCH"] else "CLEAR",
                    "duplicate_invoice_found": duplicate,
                    "bank_account_compared_by_blind_index": bool(bank_field and vendor),
                },
                "policy_clauses": policies,
                "reference_source": reference_source,
                "unresolved_items": [
                    code
                    for code in reason_codes
                    if code
                    in {
                        "MISSING_VERIFIED_PO",
                        "MISSING_ACCEPTED_GRN",
                        "VENDOR_UNRESOLVED",
                        "BANK_ACCOUNT_UNVERIFIED",
                        "TAX_POLICY_UNVERIFIED",
                    }
                ],
            }
            evidence_hash = canonical_hash(packet)

            evidence_rows = [
                EvidenceItem(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    run_id=run_id,
                    source_type="DOCUMENT_PARSER",
                    source_id=str(invoice_document.document_id),
                    source_locator={"document_id": str(invoice_document.document_id)},
                    claim=(
                        f"Invoice {extracted_invoice['invoice_number']} extracted locally with "
                        f"{len(extracted_invoice['line_items'])} line items."
                    ),
                    reason_code="INVOICE_EXTRACTED",
                    confidence=0.85,
                ),
                EvidenceItem(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    run_id=run_id,
                    source_type="THREE_WAY_MATCH",
                    source_id=reference_source,
                    source_locator={
                        "po_number": po_data.get("po_number"),
                        "line_count": len(match_result["line_matches"]),
                    },
                    claim=f"Three-way match disposition: {match_result['match_status']}.",
                    reason_code=match_result["match_status"],
                    confidence=1.0,
                ),
            ]
            session.add_all(evidence_rows)
            for exception in exceptions:
                session.add(
                    InvoiceException(
                        tenant_id=tenant_id,
                        case_id=case_id,
                        invoice_id=invoice_record.invoice_id,
                        exception_type=exception["exception_type"],
                        severity=exception["severity"],
                        mismatch_details=exception["mismatch_details"],
                        variance_amount=float(variance_amount),
                        variance_pct=float(variance_pct),
                        tolerance_threshold_amount=float(threshold_amount),
                        tolerance_threshold_pct=float(threshold_pct),
                        within_tolerance=within_tolerance,
                        resolution_status="OPEN",
                        policy_reference=canonical_hash(policies),
                    )
                )

            await session.flush()
            graph_packet = {
                "_data_classification": settings.LLM_DATA_CLASSIFICATION,
                "recommendation": recommendation,
                "reason_codes": reason_codes,
                "unresolved_items": packet["unresolved_items"],
                "deterministic_checks": {
                    "duplicate_invoice": (
                        "REVIEW_REQUIRED" if duplicate else "CLEAR"
                    ),
                    "bank_change": (
                        "BLOCKED"
                        if bank_mismatch
                        else "UNVERIFIED"
                        if bank_unverified
                        else "CLEAR"
                    ),
                    "three_way_match": match_result["match_status"],
                    "within_tolerance": within_tolerance,
                },
                "evidence": [
                    {
                        "evidence_id": str(evidence.evidence_item_id),
                        "source_type": evidence.source_type,
                        "reason_code": evidence.reason_code,
                        "tokenized_claim": (
                            "The invoice was extracted by the local parser."
                            if evidence.source_type == "DOCUMENT_PARSER"
                            else evidence.claim
                        ),
                    }
                    for evidence in evidence_rows
                ],
                "policy_citations": [
                    (
                        f"{item['policy_version_id']}:"
                        f"{item['clause_id']}"
                    )
                    for item in policies
                ],
                "packet_hash": evidence_hash,
            }
            graph_state = {
                "tenant_id": str(tenant_id),
                "case_id": str(case_id),
                "run_id": str(run_id),
                "workflow_kind": "invoice",
                "evidence_hash": evidence_hash,
                "case_version": case.current_version + 1,
                "human_gate_kind": (
                    "CLARIFICATION"
                    if missing_po or not vendor
                    else "APPROVAL"
                ),
                "required_reviews": [
                    review_type
                    for review_type, required in (
                        ("DUPLICATE_REVIEW", duplicate),
                        ("BANK_CHANGE_REVIEW", bank_mismatch),
                        ("TAX_REVIEW", "TAX_MISMATCH" in reason_codes),
                        (
                            "PROCUREMENT_REVIEW",
                            bool(exceptions)
                            and not (
                                duplicate
                                or bank_mismatch
                                or "TAX_MISMATCH" in reason_codes
                            ),
                        ),
                    )
                    if required
                ],
                "completed_reviews": [],
                "deterministic_packet": graph_packet,
                "current_stage": "deterministic_checks_complete",
            }
            async with tenant_workflow(str(tenant_id)) as graph:
                graph_result = await graph.ainvoke(
                    graph_state,
                    workflow_config(run.thread_id),
                )
            run.model_name = settings.DEFAULT_MODEL
            run.prompt_version = "enterprise-evidence-v1"
            run.input_hash = evidence_hash
            run.state_json = {
                **run.state_json,
                "evidence_hash": evidence_hash,
                "recommendation": recommendation,
                "reason_codes": reason_codes,
                "current_stage": graph_result["current_stage"],
                "blocker": graph_result.get("blocker"),
                "contradiction_result": graph_result.get(
                    "contradiction_result"
                ),
                "verification_result": graph_result.get(
                    "verification_result"
                ),
                "critique_result": graph_result.get("critique_result"),
            }
            run.state_version += 1

            if graph_result.get("blocker"):
                case.status = CaseStatus.VERIFICATION_FAILED
                case.current_version += 1
                run.status = "BLOCKED"
                run.current_node = graph_result["current_stage"]
                await append_case_event(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    event_type="AGENT_BLOCKED",
                    actor_type="SYSTEM",
                    actor_id="invoice-worker",
                    payload={
                        "run_id": str(run_id),
                        **graph_result["blocker"],
                    },
                )
            elif missing_po or not vendor:
                await _request_clarification(
                    session,
                    tenant_id=tenant_id,
                    case=case,
                    run=run,
                    reason_code="MANDATORY_REFERENCE_MISSING",
                    questions=[
                        {
                            "question_id": code.lower(),
                            "text": f"Resolve mandatory control: {code}.",
                            "field_name": code.lower(),
                            "requested_from_role": "requester",
                        }
                        for code in reason_codes
                        if code in {"MISSING_VERIFIED_PO", "VENDOR_UNRESOLVED"}
                    ],
                )
            else:
                interrupt_value = graph_result["__interrupt__"][0].value
                task_type = (
                    interrupt_value["review_type"]
                    if interrupt_value["kind"] == "CONTROL_REVIEW"
                    else "INVOICE_AP_APPROVAL"
                )
                if task_type == "DUPLICATE_REVIEW":
                    case.status = CaseStatus.BLOCKED_DUPLICATE
                elif interrupt_value["kind"] == "CONTROL_REVIEW":
                    case.status = CaseStatus.HOLD
                else:
                    case.status = CaseStatus.APPROVAL_PENDING
                case.current_version += 1
                run.status = "INTERRUPTED"
                run.current_node = (
                    "control_review"
                    if interrupt_value["kind"] == "CONTROL_REVIEW"
                    else "approval_interrupt"
                )
                assigned_role = {
                    "DUPLICATE_REVIEW": "procurement_approver",
                    "BANK_CHANGE_REVIEW": "finance_approver",
                    "TAX_REVIEW": "finance_approver",
                    "PROCUREMENT_REVIEW": "procurement_approver",
                    "INVOICE_AP_APPROVAL": "finance_approver",
                }[task_type]
                session.add(
                    ApprovalTask(
                        tenant_id=tenant_id,
                        case_id=case_id,
                        run_id=run_id,
                        task_type=task_type,
                        status="PENDING",
                        assigned_role=assigned_role,
                        proposed_action={
                            "action": "RESOLVE_INVOICE_EXCEPTION",
                            "payload": {
                                "invoice_id": str(invoice_record.invoice_id),
                                "recommendation": recommendation,
                            },
                        },
                        evidence_packet=packet,
                        evidence_hash=evidence_hash,
                        case_version=case.current_version,
                    )
                )
                await append_case_event(
                    session,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    event_type="APPROVAL_REQUIRED",
                    actor_type="SYSTEM",
                    actor_id="invoice-worker",
                    payload={
                        "run_id": str(run_id),
                        "reason_codes": reason_codes,
                        "evidence_hash": evidence_hash,
                    },
                )
            await append_audit(
                session,
                tenant_id=tenant_id,
                case_id=case_id,
                actor_type="SYSTEM",
                actor_id="invoice-worker",
                action="INVOICE_ANALYSIS_COMPLETED",
                resource_type="AGENT_RUN",
                resource_id=str(run_id),
                metadata={
                    "evidence_hash": evidence_hash,
                    "reason_codes": reason_codes,
                    "reference_source": reference_source,
                },
            )
            session.add(InboxReceipt(consumer_name="invoice-worker", event_id=event_id, tenant_id=tenant_id))


async def dispatch(envelope: dict[str, Any]) -> None:
    if envelope["event_type"] == "invoice.submitted.v1":
        await handle_invoice_submitted(envelope)
    elif envelope["event_type"] == "invoice.analysis.requested.v1":
        await run_invoice_analysis(envelope)


if __name__ == "__main__":
    asyncio.run(
        consume(
            "invoice-worker",
            ["invoice.submitted.v1", "invoice.analysis.requested.v1"],
            dispatch,
        )
    )
