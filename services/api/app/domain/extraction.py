"""Deterministic field and table extraction from document text.

The previous extractor matched only ``Label: value`` on a single line. Real
documents - including every PDF in the shipped corpus - put the label on one
line and the value on the next, and wrap long labels across two lines
("Business registration" / "number"). That extractor therefore found almost
nothing, and the workflow above it drew conclusions from an empty field set.

This module handles the three forms that actually occur:

    Legal name: Acme (Pvt) Ltd        inline, colon-separated
    Legal name                        label line, value on the next line
    Acme (Pvt) Ltd
    Business registration             label wrapped across two lines
    number
    PV 198423

Everything here is deterministic and pure. Nothing calls a model. That is a
requirement rather than a preference: extraction feeds the controls, and a
control whose inputs an LLM can influence is not a control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# --- Label vocabulary -------------------------------------------------------

# Canonical field name -> labels that introduce it, most specific first.
# Matching is on the whole normalized label, so "country" cannot swallow
# "bank country".
LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    # Identity
    "legal_name": (
        "legal name",
        "legal entity",
        "registered entity",
        "insured",
        "entity name",
    ),
    "registration_no": (
        "business registration number",
        "registration number",
        "registration no",
        "company registration number",
    ),
    "tax_id": (
        "tax identification number",
        "supplier tax id",
        "tax id",
        "taxpayer identification number",
        "tin",
    ),
    "registered_country": (
        "country of registration",
        "country of incorporation",
        "registered country",
        "country",
    ),
    "registered_address": (
        "registered address",
        "supplier address",
        "address",
    ),
    "email": ("email", "email address", "e-mail"),
    "telephone": ("telephone", "phone", "contact number"),
    "primary_contact": ("primary contact", "contact person"),
    "supplier_category": ("supplier category", "category"),
    # Commercial
    "annual_spend": ("annual spend", "estimated annual spend", "annual value"),
    "payment_terms": ("payment terms", "terms of payment"),
    "preferred_currency": ("preferred currency",),
    "currency": ("account currency", "currency"),
    "company_data_access": (
        "company data access",
        "data access",
        "access to company data",
    ),
    "subcontractors": ("subcontractors", "use of subcontractors"),
    # Banking
    "bank_beneficiary_name": (
        "beneficiary name",
        "beneficiary",
        "account holder",
        "payee",
    ),
    "bank_name": ("bank name", "bank"),
    "bank_branch": ("branch",),
    "bank_account": ("account number", "iban", "account no"),
    "bank_country": ("bank country", "country of bank"),
    "swift_code": ("swift code", "swift", "bic"),
    # Certificates and validity
    "policy_number": ("policy number",),
    "insurance_period": ("period of insurance", "period of cover"),
    "cover_type": ("type of cover",),
    "certificate_valid_until": (
        "certificate valid until",
        "valid until",
        "expiry date",
        "date of expiry",
    ),
    "effective_date": ("effective date", "date of issue", "date issued"),
    "status": ("tax status", "status"),
    # Ownership
    "beneficial_owner": ("declared beneficial owner", "beneficial owner"),
    "ownership_percentage": ("ownership or control", "ownership percentage"),
    "politically_exposed_person": ("politically exposed person declaration",),
    # Invoice / PO / GRN
    "invoice_number": ("invoice number", "invoice no"),
    "invoice_date": ("invoice date",),
    "due_date": ("due date", "payment due date"),
    "po_number": ("purchase order number", "purchase order", "po number", "po ref"),
    "order_date": ("order date",),
    "grn_number": ("receipt number", "goods receipt number", "grn number"),
    "receipt_date": ("receipt date", "date received"),
    "supplier_name": ("supplier",),
    "bill_to": ("bill to", "invoice to"),
    "deliver_to": ("deliver to", "delivery address"),
    "received_by": ("received by",),
    "payment_reference": ("payment reference",),
    # Totals
    "subtotal": ("subtotal", "sub total", "net amount"),
    "gross_amount": (
        "amount due",
        "order total",
        "invoice total",
        "total amount",
        "grand total",
    ),
}

# Labels that are never a value, so a label line immediately following another
# label line means the first label had no value.
_ALL_LABELS = {alias for aliases in LABEL_ALIASES.values() for alias in aliases}

_TAX_LABEL = re.compile(r"^tax\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)$", re.I)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)
_MONEY = re.compile(
    r"^(?:([A-Z]{3})\s*)?([0-9][0-9,\s]*(?:\.[0-9]{1,4})?)$",
    re.I,
)
_PERIOD = re.compile(r"^(.+?)\s+to\s+(.+)$", re.I)


@dataclass(frozen=True)
class LabelledValue:
    """A value together with where in the document it was found."""

    value: str
    line_index: int
    label: str
    form: str  # "inline" | "next-line" | "wrapped-label"


@dataclass(frozen=True)
class LineItem:
    line_number: int | None
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    quantity_received: Decimal | None = None
    condition: str | None = None
    currency: str | None = None
    # Columns the header declared but this row did not yield a usable value
    # for. Partial extraction has to be visible, not silently matched on.
    unparsed_columns: tuple[str, ...] = ()


@dataclass
class ExtractionResult:
    fields: dict[str, LabelledValue] = field(default_factory=dict)
    line_items: list[LineItem] = field(default_factory=list)
    tax_rate_percent: Decimal | None = None
    tax_amount: Decimal | None = None
    line_item_extraction_complete: bool = True

    def value(self, name: str) -> str | None:
        found = self.fields.get(name)
        return found.value if found else None


# --- Normalisation helpers --------------------------------------------------


def normalize_label(text: str) -> str:
    """Reduce a label to a comparable form: lowercase, no punctuation noise."""
    collapsed = " ".join(text.split()).lower()
    return collapsed.rstrip(":.-").strip()


def _looks_like_label(line: str) -> bool:
    return normalize_label(line) in _ALL_LABELS


# Page furniture that sits between a document's category heading and its body.
# Without this, a purchase order whose header reads "Purchase order / Page 1"
# yields po_number="Page 1" - a confident, wrong answer that then flows into
# three-way matching.
_NON_VALUES = re.compile(r"^page\s+\d+(\s+of\s+\d+)?$", re.I)


def _is_non_value(line: str) -> bool:
    return bool(_NON_VALUES.match(normalize_label(line)))


# ISO 3166-1 alpha-2 for the jurisdictions the corpus and policies use. An
# unknown country returns None rather than a guess: a wrong country code in a
# cross-border control is worse than an absent one, because it produces a
# confident answer to a question that was never actually answered.
_COUNTRY_CODES: dict[str, str] = {
    "sri lanka": "LK",
    "lk": "LK",
    "singapore": "SG",
    "sg": "SG",
    "hong kong": "HK",
    "hong kong sar": "HK",
    "hk": "HK",
    "india": "IN",
    "in": "IN",
    "united arab emirates": "AE",
    "uae": "AE",
    "ae": "AE",
    "united kingdom": "GB",
    "uk": "GB",
    "gb": "GB",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "malaysia": "MY",
    "my": "MY",
    "china": "CN",
    "cn": "CN",
    "australia": "AU",
    "au": "AU",
    "germany": "DE",
    "de": "DE",
    "netherlands": "NL",
    "nl": "NL",
    "japan": "JP",
    "jp": "JP",
    "pakistan": "PK",
    "pk": "PK",
    "bangladesh": "BD",
    "bd": "BD",
    "maldives": "MV",
    "mv": "MV",
}


def normalize_country(value: str | None) -> str | None:
    """Map a country name or code to ISO 3166-1 alpha-2, or None if unknown."""
    if not value:
        return None
    key = " ".join(value.split()).lower().strip(".,")
    return _COUNTRY_CODES.get(key)


_DATE_FORMATS = (
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    candidate = " ".join(value.split()).strip(".,")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def parse_period(value: str | None) -> tuple[date | None, date | None]:
    """Parse "01 September 2024 to 31 August 2025" into its two endpoints."""
    if not value:
        return None, None
    match = _PERIOD.match(" ".join(value.split()))
    if not match:
        return parse_date(value), None
    return parse_date(match.group(1)), parse_date(match.group(2))


def parse_money(value: str | None) -> tuple[str | None, Decimal | None]:
    """Parse "LKR 1,250,000.00" into ("LKR", Decimal("1250000.00"))."""
    if not value:
        return None, None
    match = _MONEY.match(" ".join(value.split()))
    if not match:
        return None, None
    currency = match.group(1).upper() if match.group(1) else None
    try:
        amount = Decimal(match.group(2).replace(",", "").replace(" ", ""))
    except InvalidOperation:
        return currency, None
    return currency, amount


def parse_quantity(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(" ".join(value.split()).replace(",", ""))
    except InvalidOperation:
        return None


def email_domain(text: str | None) -> str | None:
    if not text:
        return None
    match = _EMAIL.search(text)
    return match.group(1).lower() if match else None


# --- Field extraction -------------------------------------------------------


def extract_labelled_fields(text: str) -> dict[str, LabelledValue]:
    """Find every known field in the document text.

    First match wins per field, scanning top to bottom, because documents put
    their authoritative statement of a fact before any later restatement of it.
    """
    lines = [line.strip() for line in text.splitlines()]
    found: dict[str, LabelledValue] = {}

    # Index each alias to the field it belongs to. Longer aliases are tried
    # first so "business registration number" wins over "registration number".
    alias_to_field: list[tuple[str, str]] = sorted(
        (
            (alias, name)
            for name, aliases in LABEL_ALIASES.items()
            for alias in aliases
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for index, line in enumerate(lines):
        if not line:
            continue
        normalized = normalize_label(line)

        for alias, name in alias_to_field:
            if name in found:
                continue

            # Form 1: "Label: value" on one line.
            inline = re.match(
                rf"^{re.escape(alias)}\s*[:\-]\s*(\S.*)$",
                line,
                re.I,
            )
            if inline:
                found[name] = LabelledValue(
                    value=" ".join(inline.group(1).split()),
                    line_index=index,
                    label=alias,
                    form="inline",
                )
                break

            # Form 2: the line is exactly the label; the value follows.
            if normalized == alias:
                value = _next_value(lines, index)
                if value is not None:
                    found[name] = LabelledValue(
                        value=value[0],
                        line_index=value[1],
                        label=alias,
                        form="next-line",
                    )
                break

            # Form 3: the label wrapped, so this line plus the next make it up.
            if index + 1 < len(lines) and lines[index + 1]:
                joined = normalize_label(f"{line} {lines[index + 1]}")
                if joined == alias:
                    value = _next_value(lines, index + 1)
                    if value is not None:
                        found[name] = LabelledValue(
                            value=value[0],
                            line_index=value[1],
                            label=alias,
                            form="wrapped-label",
                        )
                    break

    return found


def _next_value(lines: list[str], label_index: int) -> tuple[str, int] | None:
    """Return the first non-empty line after the label that is not itself a label."""
    for offset in range(label_index + 1, min(label_index + 3, len(lines))):
        candidate = lines[offset]
        if not candidate:
            continue
        if _looks_like_label(candidate) or _is_non_value(candidate):
            return None
        return " ".join(candidate.split()), offset
    return None


# --- Table extraction -------------------------------------------------------

# Header cell -> the LineItem attribute it populates.
_COLUMN_ROLES: dict[str, str] = {
    "line": "line_number",
    "item": "line_number",
    "#": "line_number",
    "description": "description",
    "item description": "description",
    "particulars": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "ordered": "quantity",
    "unit price": "unit_price",
    "rate": "unit_price",
    "line total": "line_total",
    "amount": "line_total",
    "total": "line_total",
    "received": "quantity_received",
    "accepted": "quantity_received",
    "condition": "condition",
}

_TABLE_TERMINATORS = re.compile(
    r"^(subtotal|sub total|tax\s*\(|total|amount due|order total|grand total|"
    r"net amount|receiving note|purchase order conditions|remittance details|"
    r"declaration|_{4,})",
    re.I,
)


def _find_header(lines: list[str]) -> tuple[int, list[str]] | None:
    """Locate a stacked table header and return its end index and column roles.

    Corpus tables render each header cell on its own line, so a header is a run
    of consecutive lines that are all recognised column names and that includes
    a description column.
    """
    for index, line in enumerate(lines):
        if normalize_label(line) not in {"line", "item", "#"}:
            continue
        roles: list[str] = []
        cursor = index
        while cursor < len(lines):
            role = _COLUMN_ROLES.get(normalize_label(lines[cursor]))
            if role is None:
                break
            roles.append(role)
            cursor += 1
        if "description" in roles and len(roles) >= 3:
            return cursor, roles
    return None


def extract_line_items(text: str) -> tuple[list[LineItem], bool]:
    """Extract table rows, and report whether every row parsed cleanly.

    The boolean matters more than it looks: if three of four rows parse, the
    caller must be able to say so and route to review rather than quietly
    matching on the three it understood.
    """
    lines = [line.strip() for line in text.splitlines()]
    header = _find_header(lines)
    if not header:
        return [], True

    cursor, roles = header
    column_count = len(roles)
    items: list[LineItem] = []
    complete = True

    while cursor < len(lines):
        line = lines[cursor]
        if not line:
            cursor += 1
            continue
        if _TABLE_TERMINATORS.match(line):
            break
        if not re.fullmatch(r"\d{1,3}", line):
            # A row must open with its line number. Anything else means the
            # table ended in a way we do not recognise.
            break

        cells: list[str] = [line]
        cursor += 1
        # Take one cell per column, then keep taking while the trailing
        # columns still fail to parse - a description wrapped onto a second
        # line pushes every numeric column right by one, and the only reliable
        # way to detect that is that the numbers stop looking like numbers.
        while cursor < len(lines) and (
            len(cells) < column_count
            or (
                len(cells) < column_count + _MAX_DESCRIPTION_OVERFLOW
                and not _trailing_columns_parse(roles, cells)
            )
        ):
            candidate = lines[cursor]
            if not candidate:
                cursor += 1
                continue
            if _TABLE_TERMINATORS.match(candidate):
                break
            cells.append(" ".join(candidate.split()))
            cursor += 1

        if len(cells) < column_count:
            complete = False
            if not cells[1:]:
                break

        item, row_complete = _build_line_item(roles, cells)
        complete = complete and row_complete
        items.append(item)

    return items, complete


# A description that wraps more than this is not a wrapped description; it is
# a table we have misread, and guessing further would invent line items.
_MAX_DESCRIPTION_OVERFLOW = 3


def _cell_parses_as(role: str, cell: str) -> bool:
    if role in {"quantity", "quantity_received", "line_number"}:
        return parse_quantity(cell) is not None
    if role in {"unit_price", "line_total"}:
        return parse_money(cell)[1] is not None
    return bool(cell)


def _trailing_columns_parse(roles: list[str], cells: list[str]) -> bool:
    """Do the cells after the description hold the column types they claim?"""
    description_at = roles.index("description")
    overflow = len(cells) - len(roles)
    remainder = cells[description_at + max(overflow, 0) + 1 :]
    trailing_roles = roles[description_at + 1 :]
    if len(remainder) < len(trailing_roles):
        return False
    return all(
        _cell_parses_as(role, cell)
        for role, cell in zip(trailing_roles, remainder, strict=False)
    )


def _build_line_item(roles: list[str], cells: list[str]) -> tuple[LineItem, bool]:
    """Assemble a row, merging any overflow cells back into the description.

    A wrapped description produces more cells than columns. The trailing cells
    are the numeric ones, so anything extra between the line number and them
    belongs to the description.
    """
    values: dict[str, str] = {}
    unparsed: list[str] = []

    description_at = roles.index("description")
    trailing = len(roles) - description_at - 1
    overflow = len(cells) - len(roles)

    if overflow > 0:
        description = " ".join(cells[description_at : description_at + overflow + 1])
        remainder = cells[description_at + overflow + 1 :]
    else:
        description = cells[description_at] if description_at < len(cells) else ""
        remainder = cells[description_at + 1 :]

    for role, cell in zip(roles[:description_at], cells[:description_at], strict=False):
        values[role] = cell
    values["description"] = description
    for role, cell in zip(roles[description_at + 1 :], remainder, strict=False):
        values[role] = cell

    if len(remainder) < trailing:
        unparsed.extend(roles[description_at + 1 + len(remainder) :])

    currency, unit_price = parse_money(values.get("unit_price"))
    line_currency, line_total = parse_money(values.get("line_total"))

    line_number = parse_quantity(values.get("line_number"))
    return (
        LineItem(
            line_number=int(line_number) if line_number is not None else None,
            description=values.get("description", ""),
            quantity=parse_quantity(values.get("quantity")),
            unit_price=unit_price,
            line_total=line_total,
            quantity_received=parse_quantity(values.get("quantity_received")),
            condition=values.get("condition"),
            currency=currency or line_currency,
            unparsed_columns=tuple(unparsed),
        ),
        not unparsed,
    )


def extract_tax_summary(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Find the stated tax rate and tax amount from a "Tax (18%)" trailer row."""
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        match = _TAX_LABEL.match(normalize_label(line))
        if not match:
            continue
        rate = Decimal(match.group(1))
        amount = None
        for offset in range(index + 1, min(index + 3, len(lines))):
            if lines[offset]:
                _, amount = parse_money(lines[offset])
                break
        return rate, amount
    return None, None


def extract(text: str) -> ExtractionResult:
    """Run every extractor over one document's text."""
    items, complete = extract_line_items(text)
    rate, amount = extract_tax_summary(text)
    return ExtractionResult(
        fields=extract_labelled_fields(text),
        line_items=items,
        tax_rate_percent=rate,
        tax_amount=amount,
        line_item_extraction_complete=complete,
    )
