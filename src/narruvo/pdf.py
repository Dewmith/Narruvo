"""Synchronous PDF implementation, called exclusively inside the PDF process."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from narruvo.domain import PackageCheckResult, PageText, PdfInfo, PdfLine, TextBlock


class PdfError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedPage:
    page_index: int
    width: int
    height: int
    stride: int
    samples: bytes


class PdfService:
    """Serial PyMuPDF service owned by the dedicated PDF process."""

    def __init__(self):
        import pymupdf

        self.module = pymupdf
        self.document = None
        self.pages: dict[int, PageText] = {}

    def verify_runtime(self, directory: str) -> PackageCheckResult:
        """Exercise native PDF resources inside the dedicated PDF process."""
        path = Path(directory) / "package-check.pdf"
        try:
            with self.module.open() as document:
                page = document.new_page()
                page.insert_text((50, 100), "Narruvo package verification.")
                document.save(path)
            info = self.open(str(path))
            page = self.extract(0)
            rendered = self.render(0, 0.5)
            _, chunks = self.finalize()
            if (info.page_count != 1 or not page.blocks or not chunks or
                    rendered.width <= 0 or rendered.height <= 0 or
                    len(rendered.samples) != rendered.height * rendered.stride):
                raise PdfError("Packaged PDF extraction or rendering failed")
            return PackageCheckResult("pdf", f"Extracted and rendered {rendered.width}x{rendered.height} RGB pixels")
        finally:
            self.close()
            path.unlink(missing_ok=True)

    def close(self) -> None:
        if self.document is not None:
            self.document.close()
            self.document = None
        self.pages.clear()

    def open(self, filename: str) -> PdfInfo:
        """Validate and hash an original PDF without copying it.

        Returns metadata or raises ``PdfError`` for unavailable, invalid,
        empty, or protected files. Opening and hashing belong in the worker.
        """
        self.close()
        path = Path(filename).expanduser().resolve()
        if not path.is_file():
            raise PdfError("The PDF could not be found. Locate the file or remove its library entry.")
        try:
            document = self.module.open(path)
            if not document.is_pdf:
                document.close()
                raise PdfError("Choose a PDF document (.pdf).")
            if document.needs_pass:
                document.close()
                raise PdfError("This PDF is password protected. Open an unlocked copy in Narruvo.")
            if not document.page_count:
                document.close()
                raise PdfError("This PDF has no pages.")
            self.document = document
            digest = sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            title = (document.metadata or {}).get("title", "").strip() or path.stem
            sizes = tuple((float(page.rect.width), float(page.rect.height)) for page in document)
            return PdfInfo(digest.hexdigest(), str(path), title, document.page_count, sizes)
        except PdfError:
            raise
        except Exception as exc:
            self.close()
            raise PdfError(f"This PDF could not be opened. It may be corrupt or unavailable. {exc}") from exc

    def _page(self, index: int):
        if self.document is None:
            raise PdfError("No PDF is open.")
        if not 0 <= index < self.document.page_count:
            raise PdfError("That page is outside the document.")
        return self.document.load_page(index)

    def extract(self, index: int) -> PageText:
        """Extract a zero-based page with physical line geometry for later cleanup."""
        page = self._page(index)
        # MuPDF can merge two columns into one block when their baselines align.
        # Inspect line boxes before accepting block order, and exclude image bytes.
        data = page.get_text("dict", flags=self.module.TEXTFLAGS_DICT & ~self.module.TEXT_PRESERVE_IMAGES)
        blocks = []
        unrotated = page.rect * page.derotation_matrix
        midpoint = unrotated.width / 2
        for block in data["blocks"]:
            if block["type"] != 0:
                continue
            lines = [(line["bbox"], "".join(span["text"] for span in line["spans"])) for line in block["lines"]]
            lines = [line for line in lines if line[1].strip()]
            if not lines:
                continue
            left = [line for line in lines if line[0][2] < midpoint]
            right = [line for line in lines if line[0][0] > midpoint]
            groups = [left, right] if left and right and len(left) + len(right) == len(lines) else [lines]
            for group in groups:
                box = (min(line[0][0] for line in group), min(line[0][1] for line in group), max(line[0][2] for line in group), max(line[0][3] for line in group))
                source_lines = tuple(PdfLine(text, tuple(self.module.Rect(bounds) * page.rotation_matrix)) for bounds, text in group)
                blocks.append(TextBlock(*box, "\n".join(line[1] for line in group), source_lines))
        blocks = tuple(blocks)
        result = PageText(index, float(unrotated.width), float(unrotated.height), blocks)
        self.pages[index] = result
        return result

    def finalize(self):
        from narruvo.text import chunk_prepared_pages, prepare_pages
        prepared = prepare_pages([self.pages[i] for i in sorted(self.pages)])
        return [(page.page_index, page.text) for page in prepared], chunk_prepared_pages(prepared)

    def render(self, index: int, scale: float) -> RenderedPage:
        """Rasterize a page to plain RGB bytes with bounded scale and pixel count."""
        page = self._page(index)
        scale = min(4.0, max(0.2, float(scale)))
        scale = min(scale, (12_000_000 / max(1, page.rect.width * page.rect.height)) ** 0.5)
        pix = page.get_pixmap(matrix=self.module.Matrix(scale, scale), colorspace=self.module.csRGB, alpha=False)
        return RenderedPage(index, pix.width, pix.height, pix.stride, pix.samples)

