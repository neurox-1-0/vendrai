from enum import StrEnum


class ExceptionType(StrEnum):
    PRICE_VARIANCE = "PRICE_VARIANCE"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    MISSING_PO = "MISSING_PO"
    TAX_ISSUE = "TAX_ISSUE"


class ExceptionSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MatchStatus(StrEnum):
    FULL_MATCH = "FULL_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    NO_MATCH = "NO_MATCH"
    MISSING_REFERENCE = "MISSING_REFERENCE"


def check_tolerance(variance_amount: float, variance_pct: float, threshold_amount: float, threshold_pct: float) -> bool:
    """
    Deterministic tolerance checking.
    An exception is within tolerance if BOTH the absolute amount variance
    AND the percentage variance are within or equal to their respective thresholds.
    """
    return abs(variance_amount) <= threshold_amount and abs(variance_pct) <= threshold_pct
