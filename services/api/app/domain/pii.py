"""Local, fail-closed PII recognition shared by OCR and the LLM gateway.

The patterns are also registered as Presidio ``PatternRecognizer`` instances
inside the document image. The regex fallback keeps the API/agent image small
and guarantees that provider payload validation does not depend on an NLP
model being available.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SensitiveSpan:
    start: int
    end: int
    entity_type: str
    score: float


PATTERNS: dict[str, tuple[re.Pattern[str], float]] = {
    "EMAIL_ADDRESS": (
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        0.95,
    ),
    "PHONE_NUMBER": (
        re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)"),
        0.75,
    ),
    "IBAN": (
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.I),
        0.95,
    ),
    "SWIFT_CODE": (
        re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
        0.9,
    ),
    "TAX_ID": (
        re.compile(
            r"(?i)\b(?:TIN|VAT|TAX(?:PAYER)?(?:\s+ID)?)"
            r"[\s:#-]*([A-Z0-9][A-Z0-9 -]{5,24})\b"
        ),
        0.85,
    ),
    "BANK_ACCOUNT": (
        re.compile(
            r"(?i)\b(?:ACCOUNT|A/C)(?:\s+(?:NO|NUMBER))?"
            r"[\s:#-]*([A-Z0-9][A-Z0-9 -]{7,32})\b"
        ),
        0.85,
    ),
    "COMPANY_REGISTRATION": (
        re.compile(
            r"(?i)\b(?:COMPANY|BUSINESS|REGISTRATION|REG)"
            r"(?:\s+(?:NO|NUMBER|ID))?[\s:#-]*"
            r"([A-Z]{0,3}\d[A-Z0-9/-]{4,24})\b"
        ),
        0.8,
    ),
}


def _regex_spans(text: str) -> list[SensitiveSpan]:
    spans: list[SensitiveSpan] = []
    for entity_type, (pattern, score) in PATTERNS.items():
        for match in pattern.finditer(text):
            spans.append(
                SensitiveSpan(
                    start=match.start(),
                    end=match.end(),
                    entity_type=entity_type,
                    score=score,
                )
            )
    return spans


def _presidio_spans(text: str) -> list[SensitiveSpan]:
    try:
        from presidio_analyzer import Pattern, PatternRecognizer
    except ImportError:
        return []
    spans: list[SensitiveSpan] = []
    for entity_type, (compiled, score) in PATTERNS.items():
        recognizer = PatternRecognizer(
            supported_entity=entity_type,
            patterns=[
                Pattern(
                    name=f"neurox_{entity_type.lower()}",
                    regex=compiled.pattern,
                    score=score,
                )
            ],
        )
        for result in recognizer.analyze(
            text=text,
            entities=[entity_type],
            nlp_artifacts=None,
        ):
            spans.append(
                SensitiveSpan(
                    start=result.start,
                    end=result.end,
                    entity_type=result.entity_type,
                    score=result.score,
                )
            )
    return spans


def detect_sensitive_spans(text: str) -> list[SensitiveSpan]:
    candidates = [*_regex_spans(text), *_presidio_spans(text)]
    candidates.sort(key=lambda item: (item.start, -(item.end - item.start)))
    selected: list[SensitiveSpan] = []
    for candidate in candidates:
        if any(
            candidate.start < existing.end
            and existing.start < candidate.end
            for existing in selected
        ):
            continue
        selected.append(candidate)
    return selected


def mask_sensitive_text(text: str) -> str:
    masked = text
    for span in reversed(detect_sensitive_spans(text)):
        masked = (
            masked[: span.start]
            + f"<{span.entity_type}>"
            + masked[span.end :]
        )
    return masked


def sensitive_entity_types(text: str) -> list[str]:
    return sorted({item.entity_type for item in detect_sensitive_spans(text)})
