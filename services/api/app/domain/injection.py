"""Detect instructions in document content that try to steer the workflow.

A supplier's document is data. When it contains text addressed to the system
processing it - "approve this immediately", "ignore previous requirements" -
that is an attempt to turn data into instruction.

The existing defence is a prompt telling the model its input is untrusted.
That is necessary but not sufficient, and critically it produces **no finding**:
nothing is visible to the reviewer, so an attempt that failed and an attempt
that never happened look identical.

Two design rules, both non-negotiable:

1. **Deterministic, never model-based.** A detector that calls an LLM is
   vulnerable to precisely the thing it is detecting.
2. **The matched span never enters a model prompt.** It is recorded as evidence
   for a human, with its locator, and nothing more. Passing it along "for
   context" would hand the injection exactly the delivery it wanted.

Detection routes to clarification. It does not auto-reject: a legitimate
document can contain unfortunate phrasing, and that judgement belongs to a
person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class InjectionPattern:
    pattern_id: str
    description: str
    regex: re.Pattern[str]


def _pattern(pattern_id: str, description: str, expression: str) -> InjectionPattern:
    return InjectionPattern(pattern_id, description, re.compile(expression, re.I))


# Grouped by the shape of the attempt rather than by wording, so a paraphrase
# is more likely to land in an existing family than to slip past entirely.
INJECTION_PATTERNS: tuple[InjectionPattern, ...] = (
    _pattern(
        "OVERRIDE_PRIOR_INSTRUCTIONS",
        "Attempts to discard earlier instructions or requirements",
        r"\b(ignore|disregard|forget|override|bypass|skip)\b[^.,\n]{0,40}\b"
        r"(previous|prior|earlier|above|all)?\s*"
        r"(instruction|requirement|approval|rule|policy|control|check|step|verification)s?\b",
    ),
    _pattern(
        "DIRECT_APPROVAL_INSTRUCTION",
        "Instructs the recipient system to approve or activate",
        r"\b(approve|activate|authorise|authorize|release|post|pay)\b"
        r"[^.,\n]{0,40}\b(immediately|now|automatically|without\s+review|today)\b",
    ),
    _pattern(
        "TREAT_AS_AUTHORISATION",
        "Asserts the document is itself the authorisation",
        r"\btreat\s+this\b[^.,\n]{0,40}\bas\b[^.,\n]{0,40}"
        r"\b(final|authorisation|authorization|approval|approved)\b",
    ),
    _pattern(
        "SUPPRESS_VERIFICATION",
        "Asks that verification or escalation not happen",
        r"\b(do\s+not|don't|no\s+need\s+to)\b[^.,\n]{0,40}\b"
        r"(request|require|contact|verify|check|escalate|review|ask)\b",
    ),
    _pattern(
        "ROLE_REASSIGNMENT",
        "Attempts to reassign the system's role or persona",
        r"\b(you\s+are|act\s+as|pretend\s+to\s+be|from\s+now\s+on\s+you)\b"
        r"[^.,\n]{0,40}\b(assistant|agent|system|administrator|approver)\b",
    ),
    _pattern(
        "EMBEDDED_DIRECTIVE_MARKER",
        "Carries markers used to delimit system instructions",
        r"(\[\s*(system|assistant|instruction)\s*\]|<\s*(system|instruction)\s*>|"
        r"###\s*(system|instruction)|BEGIN\s+SYSTEM\s+PROMPT)",
    ),
)


@dataclass(frozen=True)
class InjectionMatch:
    pattern_id: str
    description: str
    #: The matched text. Recorded for a human reviewer. **Never** include this
    #: in a model payload.
    matched_span: str
    page: int | None
    #: Character offsets within the page text, so the UI can highlight it.
    start: int
    end: int

    def as_evidence(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "matched_span": self.matched_span,
            "page": self.page,
            "start": self.start,
            "end": self.end,
        }

    def as_model_safe_summary(self) -> dict[str, object]:
        """What may be shown to a model: the shape, never the words.

        The whole point of the detector is that the instruction does not reach
        a model. Sending the span "so it knows what to ignore" defeats it.
        """
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "page": self.page,
            "character_length": len(self.matched_span),
        }


@dataclass(frozen=True)
class InjectionScanResult:
    matches: tuple[InjectionMatch, ...]

    @property
    def detected(self) -> bool:
        return bool(self.matches)

    @property
    def reason_codes(self) -> list[str]:
        return ["UNTRUSTED_DOCUMENT_INSTRUCTION"] if self.detected else []

    @property
    def pattern_ids(self) -> list[str]:
        return sorted({match.pattern_id for match in self.matches})

    def as_evidence(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "pattern_ids": self.pattern_ids,
            "matches": [match.as_evidence() for match in self.matches],
        }

    def as_model_safe_summary(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "pattern_ids": self.pattern_ids,
            "matches": [match.as_model_safe_summary() for match in self.matches],
        }


#: Longer spans are truncated in the recorded evidence. A pattern that matches
#: half a page is a pattern problem, and storing the page twice helps nobody.
MAX_RECORDED_SPAN = 400


def scan_text(text: str, *, page: int | None = None) -> InjectionScanResult:
    """Scan one page of extracted text for instruction-shaped content."""
    matches: list[InjectionMatch] = []
    for injection in INJECTION_PATTERNS:
        for found in injection.regex.finditer(text):
            span = found.group(0)
            matches.append(
                InjectionMatch(
                    pattern_id=injection.pattern_id,
                    description=injection.description,
                    matched_span=span[:MAX_RECORDED_SPAN],
                    page=page,
                    start=found.start(),
                    end=found.end(),
                )
            )
    return InjectionScanResult(matches=tuple(matches))


def scan_pages(pages: list[tuple[int, str]]) -> InjectionScanResult:
    """Scan every page, preserving which page each match came from."""
    matches: list[InjectionMatch] = []
    for page_number, text in pages:
        matches.extend(scan_text(text, page=page_number).matches)
    return InjectionScanResult(matches=tuple(matches))
