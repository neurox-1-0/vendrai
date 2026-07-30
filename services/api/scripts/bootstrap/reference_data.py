"""Load the vendor master and invoice history.

These represent an external system of record, not user-created content, so
there is no public interface to create them and none should be invented. They
are written directly - the one place in the bootstrap where that is correct.

**The detail that silently breaks everything:** ``Vendor`` stores ``tax_id`` and
``bank_account`` as blind indexes, not plaintext. A loader that writes the raw
value into those columns produces a vendor master that looks populated and
matches nothing, because duplicate detection compares HMACs. VO-002 then fails
with no error at all. :func:`verify_blind_indexes` exists specifically to make
that failure loud.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.config import settings
from app.domain.security import blind_index, normalize_vendor_name
from app.models import InvoiceHistoryRecord, Vendor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VENDOR_MASTER = Path("ground_truth/existing_vendor_master.csv")
INVOICE_HISTORY = Path("ground_truth/existing_invoice_history.csv")


class ReferenceDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadCounts:
    created: int
    updated: int

    @property
    def total(self) -> int:
        return self.created + self.updated


def _read_rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise ReferenceDataError(
            f"Reference data missing: {path}. The corpus is mounted at "
            f"{settings.CORPUS_ROOT}; check the read-only mount in "
            "docker-compose.yml."
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            {key: (value or "").strip() for key, value in row.items() if key}
            for row in csv.DictReader(handle)
        ]
    if not rows:
        raise ReferenceDataError(f"Reference data file is empty: {path}")
    missing = required - set(rows[0])
    if missing:
        raise ReferenceDataError(
            f"{path.name} is missing required column(s): {sorted(missing)}"
        )
    return rows


def _country_from(row: dict[str, str]) -> str | None:
    """The shipped master has no country column; keep the field honest."""
    value = row.get("registered_country") or row.get("country")
    return value.upper()[:2] if value else None


async def load_vendor_master(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    corpus_root: Path,
) -> LoadCounts:
    rows = _read_rows(
        corpus_root / VENDOR_MASTER,
        {"vendor_id", "legal_name", "tax_id", "bank_account", "email_domain", "status"},
    )
    existing = {
        vendor.erp_vendor_id: vendor
        for vendor in (
            await session.execute(select(Vendor).where(Vendor.tenant_id == tenant_id))
        ).scalars()
        if vendor.erp_vendor_id
    }

    created = updated = 0
    for row in rows:
        erp_vendor_id = row["vendor_id"]
        vendor = existing.get(erp_vendor_id)
        if vendor is None:
            vendor = Vendor(tenant_id=tenant_id, erp_vendor_id=erp_vendor_id)
            session.add(vendor)
            created += 1
        else:
            updated += 1
        vendor.legal_name = row["legal_name"]
        vendor.normalized_legal_name = normalize_vendor_name(row["legal_name"])
        vendor.tax_id_hash = (
            blind_index(row["tax_id"], settings.BLIND_INDEX_SECRET)
            if row["tax_id"]
            else None
        )
        vendor.bank_account_hash = (
            blind_index(row["bank_account"], settings.BLIND_INDEX_SECRET)
            if row["bank_account"]
            else None
        )
        vendor.email_domain = row["email_domain"].lower() or None
        vendor.registered_country = _country_from(row)
        vendor.status = row["status"] or "ACTIVE"
    await session.flush()
    return LoadCounts(created=created, updated=updated)


async def verify_blind_indexes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    corpus_root: Path,
) -> None:
    """Prove a known CSV tax ID reproduces the stored blind index.

    Without this the most likely loader bug - writing plaintext, or hashing
    with the wrong secret - is completely silent: duplicate detection simply
    never matches, and the scenario that depends on it appears to pass.
    """
    rows = _read_rows(corpus_root / VENDOR_MASTER, {"vendor_id", "tax_id"})
    probe = next((row for row in rows if row["tax_id"]), None)
    if probe is None:
        raise ReferenceDataError(
            "No vendor in the master carries a tax ID, so the blind-index "
            "round trip cannot be verified."
        )
    expected = blind_index(probe["tax_id"], settings.BLIND_INDEX_SECRET)
    stored = await session.scalar(
        select(Vendor.tax_id_hash).where(
            Vendor.tenant_id == tenant_id,
            Vendor.erp_vendor_id == probe["vendor_id"],
        )
    )
    if stored != expected:
        raise ReferenceDataError(
            f"Blind index mismatch for vendor {probe['vendor_id']}. The stored "
            "hash does not reproduce from the CSV value, so duplicate "
            "detection will never match and VO-002 will fail with no error. "
            "Check that BLIND_INDEX_SECRET has not changed since the last load."
        )


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", "")) if value else Decimal("0")
    except InvalidOperation as error:
        raise ReferenceDataError(f"Unparseable amount in invoice history: {value!r}") from error


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as error:
        raise ReferenceDataError(
            f"Unparseable date in invoice history: {value!r} (expected YYYY-MM-DD)"
        ) from error


async def load_invoice_history(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    corpus_root: Path,
) -> LoadCounts:
    rows = _read_rows(
        corpus_root / INVOICE_HISTORY,
        {"vendor_id", "invoice_number", "invoice_date", "gross_amount", "currency", "status"},
    )
    existing = {
        (record.vendor_id, record.invoice_number): record
        for record in (
            await session.execute(
                select(InvoiceHistoryRecord).where(
                    InvoiceHistoryRecord.tenant_id == tenant_id
                )
            )
        ).scalars()
    }

    created = updated = 0
    for row in rows:
        # vendor_id here is the ERP string (V000184), not a foreign key - it
        # matches the existing model, which mirrors how an ERP export arrives.
        key = (row["vendor_id"], row["invoice_number"])
        record = existing.get(key)
        if record is None:
            record = InvoiceHistoryRecord(
                tenant_id=tenant_id,
                vendor_id=row["vendor_id"],
                invoice_number=row["invoice_number"],
            )
            session.add(record)
            created += 1
        else:
            updated += 1
        record.invoice_date = _date(row["invoice_date"])
        record.gross_amount = _decimal(row["gross_amount"])
        record.currency = (row["currency"] or "LKR").upper()[:3]
        record.po_number = row.get("po_number") or None
        record.status = row["status"] or "PAID"
    await session.flush()
    return LoadCounts(created=created, updated=updated)


async def counts(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[int, int]:
    vendors = len(
        (
            await session.execute(
                select(Vendor.vendor_id).where(Vendor.tenant_id == tenant_id)
            )
        ).all()
    )
    history = len(
        (
            await session.execute(
                select(InvoiceHistoryRecord.record_id).where(
                    InvoiceHistoryRecord.tenant_id == tenant_id
                )
            )
        ).all()
    )
    return vendors, history
