import re
from dataclasses import dataclass, field


PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.I),
    "SWIFT": re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"),
    "TAX_ID": re.compile(r"\b(?:\d[ -]?){8,12}\b"),
    "PHONE": re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d"),
    "ACCOUNT": re.compile(r"\b\d{10,18}\b"),
}


@dataclass
class TokenizationResult:
    text: str
    token_map: dict[str, str] = field(default_factory=dict)


def tokenize_sensitive_text(text: str) -> TokenizationResult:
    token_map: dict[str, str] = {}
    masked = text
    for entity_type, pattern in PATTERNS.items():
        def replace(match: re.Match[str]) -> str:
            token = f"<{entity_type}_{sum(key.startswith(f'<{entity_type}_') for key in token_map) + 1}>"
            token_map[token] = match.group(0)
            return token
        masked = pattern.sub(replace, masked)
    return TokenizationResult(masked, token_map)


def assert_llm_payload_safe(payload: str) -> None:
    leaks = [entity for entity, pattern in PATTERNS.items() if pattern.search(payload)]
    if leaks:
        raise ValueError(f"LLM payload contains unmasked sensitive entities: {', '.join(leaks)}")
