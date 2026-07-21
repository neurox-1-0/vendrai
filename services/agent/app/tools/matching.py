import time
from typing import Any

from app.domain.invoices import MatchStatus
from app.invoice_schemas import ExtractedInvoice, LineMatch, ThreeWayMatchResult
from app.schemas import ToolResult, ToolStatus


def perform_3way_match(
    invoice: ExtractedInvoice,
    po_data: dict[str, Any] | None,
    grn_data_list: list[dict[str, Any]] | None,
    idempotency_key: str,
) -> ToolResult[ThreeWayMatchResult]:
    """
    Deterministic 3-way matching logic.
    Compares Invoice against PO (Purchase Order) and GRN (Goods Receipt Note).
    """
    started = time.perf_counter()
    
    if not po_data:
        return ToolResult(
            status=ToolStatus.FAILED,
            error_code="MISSING_PO",
            error_message="Purchase order data not provided or found.",
            provider_version="match-engine-v1",
            idempotency_key=idempotency_key,
            latency_ms=round((time.perf_counter() - started) * 1000)
        )

    grns = grn_data_list or []
    po_lines = po_data.get("lines", [])
    
    line_matches: list[LineMatch] = []
    total_variance_amount = 0.0
    
    # Map PO lines for easy lookup
    po_lines_map = {str(line.get("line_number")): line for line in po_lines}
    
    # Map GRN lines for easy lookup (aggregate by PO line)
    grn_lines_map = {}
    for grn in grns:
        for grn_line in grn.get("lines", []):
            po_ref = str(grn_line.get("po_line_id", ""))
            if po_ref:
                grn_lines_map[po_ref] = grn_lines_map.get(po_ref, 0) + grn_line.get("quantity_received", 0)

    matched_po_line_keys = set()
    unmatched_invoice_lines = []
    
    overall_status = MatchStatus.FULL_MATCH
    
    for inv_line in invoice.line_items:
        po_ref = inv_line.po_line_ref
        
        # Simple heuristic if po_line_ref is missing: try matching by line_number
        if not po_ref:
            po_ref = str(inv_line.line_number)
            
        po_line = po_lines_map.get(po_ref)
        
        if not po_line:
            unmatched_invoice_lines.append(inv_line)
            overall_status = MatchStatus.PARTIAL_MATCH
            line_matches.append(LineMatch(
                invoice_line=inv_line,
                po_line=None,
                grn_line=None,
                match_status=MatchStatus.MISSING_REFERENCE,
                signals={"reason": "PO line not found"}
            ))
            continue
            
        matched_po_line_keys.add(po_ref)
        
        # Calculate variances
        po_price = float(po_line.get("unit_price", 0))
        inv_price = float(inv_line.unit_price)
        price_var = inv_price - po_price
        
        po_qty = float(po_line.get("quantity", 0))
        grn_qty = float(grn_lines_map.get(po_line.get("po_line_id", po_ref), 0))
        inv_qty = float(inv_line.quantity)
        
        # Assuming we only pay for what we received (GRN qty) if GRN exists, else PO qty
        expected_qty = grn_qty if grns else po_qty
        qty_var = inv_qty - expected_qty
        
        status = MatchStatus.FULL_MATCH
        if price_var != 0 or qty_var != 0:
            status = MatchStatus.PARTIAL_MATCH
            overall_status = MatchStatus.PARTIAL_MATCH
            
        line_var_amt = abs(price_var) * inv_qty + abs(qty_var) * po_price
        total_variance_amount += line_var_amt
            
        line_matches.append(LineMatch(
            invoice_line=inv_line,
            po_line=po_line,
            grn_line={"quantity_received": grn_qty} if grns else None,
            price_variance=price_var,
            quantity_variance=qty_var,
            match_status=status
        ))

    unmatched_po_lines = [line for key, line in po_lines_map.items() if key not in matched_po_line_keys]
    if unmatched_po_lines:
        overall_status = MatchStatus.PARTIAL_MATCH

    # Calculate overall variance pct (against PO total)
    po_total = float(po_data.get("total_amount", 1))
    po_total = po_total if po_total > 0 else 1 # prevent div by zero
    overall_variance_pct = (total_variance_amount / po_total) * 100.0

    result = ThreeWayMatchResult(
        match_status=overall_status,
        line_matches=line_matches,
        overall_variance_amount=total_variance_amount,
        overall_variance_pct=overall_variance_pct,
        unmatched_invoice_lines=unmatched_invoice_lines,
        unmatched_po_lines=unmatched_po_lines
    )
    
    return ToolResult(
        status=ToolStatus.SUCCESS,
        data=result,
        provider_version="match-engine-v1",
        idempotency_key=idempotency_key,
        latency_ms=round((time.perf_counter() - started) * 1000)
    )
