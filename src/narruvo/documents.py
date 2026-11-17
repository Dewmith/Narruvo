"""GUI-facing asynchronous PDF coordinator with incremental extraction."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from narruvo.domain import PdfInfo
from narruvo.workers import ProcessWorker


class DocumentController(QObject):
    """Coordinate PDF work asynchronously while rejecting stale document results."""

    opened = Signal(object)
    rendered = Signal(object)
    text_ready = Signal(object, object)
    extraction_progress = Signal(int, int)
    error = Signal(str)

    def __init__(self, data_root: Path, parent=None):
        super().__init__(parent)
        self.worker = ProcessWorker("pdf", data_root, self)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._failed)
        self.generation = 0
        self.jobs: dict[int, tuple] = {}
        self.info: PdfInfo | None = None
        self.render_key = None

    def open(self, filename: str) -> None:
        """Invalidate the previous generation and queue an original PDF for opening."""
        self.generation += 1
        self.jobs.clear()
        self.worker.cancel_pending()
        self.info = None
        self.render_key = None
        self._submit("open", filename)

    def unload(self) -> None:
        self.generation += 1
        self.jobs.clear()
        self.worker.cancel_pending()
        self.info = None
        self._submit("close")

    def _submit(self, operation: str, *arguments, priority: bool = False) -> None:
        job = self.worker.submit(operation, *arguments, priority=priority)
        self.jobs[job] = (self.generation, operation, arguments)

    def render(self, page_index: int, scale: float) -> None:
        """Request a page raster, superseding pending renders and checking its recipe."""
        if not self.info:
            return
        for job in self.worker.cancel_pending("render"):
            self.jobs.pop(job, None)
        self.render_key = (page_index, scale)
        self._submit("render", page_index, scale, priority=True)

    def _result(self, job: int, value) -> None:
        metadata = self.jobs.pop(job, None)
        if not metadata or metadata[0] != self.generation:
            return
        _, operation, arguments = metadata
        if operation == "open":
            self.info = value
            self.opened.emit(value)
            self.extraction_progress.emit(0, value.page_count)
            self._submit("extract", 0)
        elif operation == "extract":
            completed = value.page_index + 1
            self.extraction_progress.emit(completed, self.info.page_count)
            if completed < self.info.page_count:
                self._submit("extract", completed)
            else:
                self._submit("finalize")
        elif operation == "finalize":
            self.text_ready.emit(*value)
        elif operation == "render" and arguments == self.render_key:
            self.rendered.emit(value)

    def _failed(self, job: int, message: str) -> None:
        metadata = self.jobs.pop(job, None)
        if metadata and metadata[0] == self.generation:
            self.error.emit(message)

    def close(self) -> None:
        self.generation += 1
        self.jobs.clear()
        self.info = None
        self.worker.shutdown()

