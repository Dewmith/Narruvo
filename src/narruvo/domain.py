"""Plain, picklable records shared by services and worker processes."""

from dataclasses import dataclass, field
from hashlib import sha256


@dataclass(frozen=True)
class PackageCheckResult:
    """Plain worker verification result and its diagnostic description."""

    component: str
    detail: str


@dataclass(frozen=True)
class PdfInfo:
    """Opened-document metadata, identified by the SHA-256 of its PDF bytes.

    Page sizes use PDF points; page and chunk indices are zero-based. The
    source path refers to an original file, not a copied document.
    """

    document_id: str
    path: str
    title: str
    page_count: int
    page_sizes: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PdfLine:
    """Extracted physical line and its rectangle in displayed-page coordinates."""

    text: str
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class TextBlock:
    """Extracted block geometry, text, and physical line mappings."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    lines: tuple[PdfLine, ...] = ()


@dataclass(frozen=True)
class PageText:
    """One extracted page before recurring-margin removal and normalization."""

    page_index: int
    width: float
    height: float
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class PageLine:
    """Half-open text offsets in a prepared page and their PDF rectangle."""

    start: int
    end: int
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class PreparedPage:
    """Normalized page text retaining source geometry for highlighting."""

    page_index: int
    text: str
    lines: tuple[PageLine, ...]


@dataclass(frozen=True)
class ReadingLine:
    """Chunk-to-page character mapping and physical PDF line rectangle."""

    start: int
    end: int
    page_start: int
    page_end: int
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class TextChunk:
    """One page-bound narration section with deterministic text identity."""

    index: int
    page_index: int
    text: str
    lines: tuple[ReadingLine, ...] = ()

    @property
    def text_hash(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class ReadingProgress:
    """Saved section, millisecond position, and active/preferred voice recipes.

    The chunk hash rejects incompatible restored offsets. Restoring this
    record does not request autoplay.
    """

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
    """A library record pointing to a user-owned PDF and its progress."""

    document_id: str
    path: str
    title: str
    page_count: int
    last_opened: str
    progress: ReadingProgress = field(default_factory=ReadingProgress)


@dataclass(frozen=True)
class SynthesisRequest:
    """Plain speech recipe containing chunk text, voice identifier, and rate."""

    text: str
    voice: str
    rate: float

    @property
    def language(self) -> str:
        return "en-gb" if self.voice.startswith("b") else "en-us"


@dataclass(frozen=True)
class SpeechCue:
    """Audio milliseconds mapped to half-open character offsets in chunk text."""

    start_ms: int
    end_ms: int
    text_start: int
    text_end: int


@dataclass(frozen=True)
class AudioResult:
    """Generated/cached WAV path, duration, and synchronized speech cues."""

    path: str
    duration_ms: int
    cache_hit: bool
    cues: tuple[SpeechCue, ...] = ()
    estimated_timings: bool = False

