import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    clause_id: str
    heading_path: list[str]
    parent_content: str
    content: str
    token_count: int


HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def approximate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def chunk_policy(content: str, child_target: int = 500, parent_target: int = 1600) -> list[Chunk]:
    """Structure-aware, sentence-boundary chunks with linked parent context."""
    sections: list[tuple[list[str], str]] = []
    headings: list[str] = []
    matches = list(HEADING.finditer(content))
    if not matches:
        sections = [([], content.strip())]
    else:
        for index, match in enumerate(matches):
            level = len(match.group(1))
            headings = headings[: level - 1] + [match.group(2).strip()]
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            sections.append((list(headings), content[start:end].strip()))
    chunks: list[Chunk] = []
    for section_index, (path, section) in enumerate(sections, start=1):
        if not section:
            continue
        sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", section)
        current: list[str] = []
        current_tokens = 0
        child_index = 1
        parent_words = section.split()[: round(parent_target / 1.3)]
        parent = " ".join(parent_words)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_tokens = approximate_tokens(sentence)
            if current and current_tokens + sentence_tokens > child_target:
                text = " ".join(current)
                chunks.append(Chunk(f"{section_index}.{child_index}", path, parent, text, approximate_tokens(text)))
                child_index += 1
                current = []
                current_tokens = 0
            current.append(sentence)
            current_tokens += sentence_tokens
        if current:
            text = " ".join(current)
            chunks.append(Chunk(f"{section_index}.{child_index}", path, parent, text, approximate_tokens(text)))
    return chunks
