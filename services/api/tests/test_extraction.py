from decimal import Decimal

from app.domain.extraction import (
    email_domain,
    extract,
    extract_labelled_fields,
    extract_line_items,
    normalize_country,
    parse_date,
    parse_money,
    parse_period,
)

ONBOARDING_FORM = """
HL
Harborline Logistics (Pvt) Ltd
12 Port Access Road, Wattala, Sri Lanka
Supplier onboarding record
Page 1
 SUPPLIER ONBOARDING FORM
Request reference: VON-2026-0720
1. Organisation details
Legal name
Harborline Logistics (Pvt) Ltd
Country
Sri Lanka
Business registration
number
PV 176402
Tax ID
116670845
Email
billing@harborline-logistics.example
2. Commercial and banking profile
Annual spend
LKR 5,900,000.00
Company data
access
No
Beneficiary
R. K. Jayawardena
Bank
Serendib Trust Bank PLC
Account number
014-600-9914
Bank country
Sri Lanka
"""

INVOICE = """
 TAX INVOICE
Invoice number
NSO-INV-2607108
Invoice date
10 July 2026
Purchase order
PO-2026-00481
Currency
LKR
Line
Description
Qty
Unit price
Amount
1
Business laptop, 14-inch, 16 GB RAM
100
LKR 12,500.00
LKR 1,250,000.00
Subtotal
LKR 1,250,000.00
Tax (18%)
LKR 225,000.00
Amount due
LKR 1,475,000.00
"""

GOODS_RECEIPT = """
 GOODS RECEIPT NOTE
Receipt number
GRN-2026-00629
Purchase order
PO-2026-00481
Line
Description
Ordered
Received
Condition
1
Business laptop, 14-inch, 16 GB RAM
100
40
Accepted
Receiving note: Received in apparent good condition
"""


def test_value_on_the_line_after_the_label_is_found():
    fields = extract_labelled_fields(ONBOARDING_FORM)
    assert fields["legal_name"].value == "Harborline Logistics (Pvt) Ltd"
    assert fields["legal_name"].form == "next-line"


def test_label_wrapped_across_two_lines_is_found():
    fields = extract_labelled_fields(ONBOARDING_FORM)
    assert fields["registration_no"].value == "PV 176402"
    assert fields["registration_no"].form == "wrapped-label"
    assert fields["company_data_access"].value == "No"


def test_inline_colon_separated_value_is_still_found():
    fields = extract_labelled_fields("Policy number: MGI-INT-2409033")
    assert fields["policy_number"].value == "MGI-INT-2409033"
    assert fields["policy_number"].form == "inline"


def test_specific_label_wins_over_a_general_one():
    """"Bank country" must not be captured as "country"."""
    fields = extract_labelled_fields(ONBOARDING_FORM)
    assert fields["registered_country"].value == "Sri Lanka"
    assert fields["bank_country"].value == "Sri Lanka"


def test_page_furniture_is_not_mistaken_for_a_value():
    """A document category heading followed by "Page 1" must yield no value.

    Purchase orders open with "Purchase order / Page 1" before the real
    "Purchase order / PO-2026-00481". Taking the first one produced a
    confident, wrong PO number that then flowed into three-way matching.
    """
    text = "Purchase order\nPage 1\n TITLE\nPurchase order\nPO-2026-00481\n"
    assert extract_labelled_fields(text)["po_number"].value == "PO-2026-00481"


def test_a_label_immediately_followed_by_another_label_yields_no_value():
    fields = extract_labelled_fields("Bank country\nBeneficiary\nAcme Ltd\n")
    assert "bank_country" not in fields


def test_invoice_line_items_carry_quantity_and_unit_price():
    items, complete = extract_line_items(INVOICE)
    assert complete is True
    assert len(items) == 1
    assert items[0].quantity == Decimal("100")
    assert items[0].unit_price == Decimal("12500.00")
    assert items[0].line_total == Decimal("1250000.00")
    assert items[0].currency == "LKR"


def test_goods_receipt_columns_map_to_received_quantity():
    items, complete = extract_line_items(GOODS_RECEIPT)
    assert complete is True
    assert items[0].quantity == Decimal("100")
    assert items[0].quantity_received == Decimal("40")
    assert items[0].condition == "Accepted"


def test_wrapped_description_does_not_shift_the_numeric_columns():
    text = (
        "Line\nDescription\nQty\nUnit price\nAmount\n"
        "1\nBusiness laptop, 14-inch,\n16 GB RAM with docking station\n"
        "100\nLKR 12,500.00\nLKR 1,250,000.00\nSubtotal\n"
    )
    items, complete = extract_line_items(text)
    assert complete is True
    assert items[0].quantity == Decimal("100")
    assert items[0].unit_price == Decimal("12500.00")
    assert "docking station" in items[0].description


def test_a_truncated_row_reports_incomplete_extraction():
    """Partial extraction must be visible, never silently matched on."""
    text = "Line\nDescription\nQty\nUnit price\nAmount\n1\nBusiness laptop\n100\nSubtotal\n"
    items, complete = extract_line_items(text)
    assert complete is False
    assert items[0].unparsed_columns


def test_tax_rate_and_amount_are_read_from_the_trailer():
    result = extract(INVOICE)
    assert result.tax_rate_percent == Decimal("18")
    assert result.tax_amount == Decimal("225000.00")


def test_money_parsing_handles_currency_prefix_and_separators():
    assert parse_money("LKR 1,250,000.00") == ("LKR", Decimal("1250000.00"))
    assert parse_money("485000") == (None, Decimal("485000"))
    assert parse_money("not stated") == (None, None)


def test_date_and_period_parsing():
    assert parse_date("10 July 2026").isoformat() == "2026-07-10"
    start, end = parse_period("01 September 2024 to 31 August 2025")
    assert start.isoformat() == "2024-09-01"
    assert end.isoformat() == "2025-08-31"


def test_unknown_country_is_none_rather_than_a_guess():
    assert normalize_country("Sri Lanka") == "LK"
    assert normalize_country("Hong Kong") == "HK"
    assert normalize_country("Freedonia") is None


def test_email_domain_is_extracted_for_the_duplicate_signal():
    assert email_domain("billing@harborline-logistics.example") == (
        "harborline-logistics.example"
    )
    assert email_domain("no address here") is None
