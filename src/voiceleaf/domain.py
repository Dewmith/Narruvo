"""Plain, picklable records shared by services and worker processes."""

from dataclasses import dataclass, field
from hashlib import sha256


@dataclass(frozen=True)
class PdfInfo:
    document_id: str
    path: str
    title: str
    page_count: int
    page_sizes: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class PageText:
    page_index: int
    width: float
    height: float
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class TextChunk:
    index: int
    page_index: int
    text: str

    @property
    def text_hash(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class ReadingProgress:
    view_page: int = 0
    chunk_index: int = 0
    position_ms: int = 0
    active_voice: str = "af_heart"
    active_rate: float = 1.0
    preferred_voice: str = "af_heart"
    preferred_rate: float = 1.0
    chunk_hash: str = ""
    completed: bool = False


@dataclass(frozen=True)
class LibraryDocument:
    document_id: str
    path: str
    title: str
    page_count: int
    last_opened: str
    progress: ReadingProgress = field(default_factory=ReadingProgress)


@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    voice: str
    rate: float

    @property
    def language(self) -> str:
        return "en-gb" if self.voice.startswith("b") else "en-us"


@dataclass(frozen=True)
class AudioResult:
    path: str
    duration_ms: int
    cache_hit: bool

