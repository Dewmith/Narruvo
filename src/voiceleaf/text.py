"""Conservative layout cleanup and deterministic page-bound narration chunks."""

import math
import re
import unicodedata
from collections import Counter

from voiceleaf.domain import PageText, TextBlock, TextChunk

PROCESSING_VERSION = "voiceleaf-text-v1"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    text = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", text)
    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", text)]
    return "\n\n".join(part for part in paragraphs if part)


def _margin(block: TextBlock, height: float) -> str | None:
    if block.y1 < height * 0.09:
        return "top"
    if block.y0 > height * 0.91:
        return "bottom"
    return None


def _signature(block: TextBlock, height: float) -> tuple[str, str, int]:
    return (_margin(block, height) or "", normalize_text(block.text).casefold(), round(block.y0 / height * 30))


def reading_order(blocks: list[TextBlock], width: float) -> list[TextBlock]:
    """Use columns only when there is a clear gutter and overlapping vertical ranges."""
    ordered = sorted(blocks, key=lambda b: (b.y0, b.x0))
    left = [b for b in blocks if b.x1 < width * 0.52 and b.x0 < width * 0.45]
    right = [b for b in blocks if b.x0 > width * 0.48]
    if len(left) < 2 or len(right) < 2:
        return ordered
    gutter_left, gutter_right = max(b.x1 for b in left), min(b.x0 for b in right)
    overlap = min(max(b.y1 for b in left), max(b.y1 for b in right)) - max(min(b.y0 for b in left), min(b.y0 for b in right))
    if gutter_right - gutter_left < width * 0.03 or overlap < 20:
        return ordered
    spanning = [b for b in ordered if b not in left and b not in right]
    result: list[TextBlock] = []
    remaining = [b for b in ordered if b in left or b in right]
    for divider in spanning:
        band = [b for b in remaining if b.y0 < divider.y0]
        result.extend(sorted((b for b in band if b in left), key=lambda b: (b.y0, b.x0)))
        result.extend(sorted((b for b in band if b in right), key=lambda b: (b.y0, b.x0)))
        remaining = [b for b in remaining if b not in band]
        result.append(divider)
    result.extend(sorted((b for b in remaining if b in left), key=lambda b: (b.y0, b.x0)))
    result.extend(sorted((b for b in remaining if b in right), key=lambda b: (b.y0, b.x0)))
    return result


def clean_pages(pages: list[PageText]) -> list[tuple[int, str]]:
    signatures: Counter = Counter()
    for page in pages:
        signatures.update({_signature(b, page.height) for b in page.blocks if _margin(b, page.height)})
    threshold = max(3, math.ceil(len(pages) * 0.7))
    repeated = {sig for sig, count in signatures.items() if count >= threshold and sig[1]}
    cleaned: list[tuple[int, str]] = []
    for page in pages:
        body: list[TextBlock] = []
        for block in page.blocks:
            value = normalize_text(block.text)
            if not value or _signature(block, page.height) in repeated:
                continue
            if _margin(block, page.height) and value == str(page.page_index + 1):
                continue
            body.append(block)
        cleaned.append((page.page_index, "\n\n".join(normalize_text(b.text) for b in reading_order(body, page.width))))
    return cleaned


def _sentences(paragraph: str) -> list[str]:
    protected = re.sub(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc)\.", lambda m: m[0].replace(".", "\uFFF0"), paragraph)
    return [part.replace("\uFFF0", ".") for part in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“])', protected)]


def _split_long(text: str, limit: int) -> list[str]:
    parts: list[str] = []
    while len(text) > limit:
        boundary = text.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        parts.append(text[:boundary].strip())
        text = text[boundary:].lstrip()
    if text:
        parts.append(text)
    return parts


def chunk_pages(pages: list[tuple[int, str]], target: int = 400, maximum: int = 600) -> list[TextChunk]:
    if not 1 <= target <= maximum:
        raise ValueError("Chunk target must be positive and no larger than the maximum")
    chunks: list[TextChunk] = []
    for page_index, raw_text in pages:
        current = ""
        for paragraph in normalize_text(raw_text).split("\n\n"):
            if not paragraph:
                continue
            for sentence in _sentences(paragraph):
                for piece in _split_long(sentence, maximum):
                    if current and (len(current) >= target or len(current) + len(piece) + 1 > maximum):
                        chunks.append(TextChunk(len(chunks), page_index, current))
                        current = ""
                    current = f"{current} {piece}".strip()
            if current and len(current) >= target:
                chunks.append(TextChunk(len(chunks), page_index, current))
                current = ""
        if current:
            chunks.append(TextChunk(len(chunks), page_index, current))
    return chunks

