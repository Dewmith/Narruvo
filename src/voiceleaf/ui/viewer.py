"""A single-page raster PDF viewer with responsive layout and a text pane."""

from PySide6.QtCore import Qt, QTimer, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStyle, QTextEdit, QVBoxLayout, QWidget

from voiceleaf.domain import PdfInfo, SpeechCue, TextChunk
from voiceleaf.pdf import RenderedPage


class PdfPageLabel(QLabel):
    """Paint a transient highlight over the raster; never modify the PDF."""

    def __init__(self, text):
        super().__init__(text)
        self.highlight_rects = ()
        self.page_size = (1.0, 1.0)

    def set_highlights(self, rectangles, page_size) -> None:
        self.highlight_rects = tuple(rectangles)
        self.page_size = page_size
        self.update()

    def highlight_bounds(self) -> tuple[QRectF, ...]:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull() or not self.highlight_rects:
            return ()
        width = pixmap.width() / pixmap.devicePixelRatioF()
        height = pixmap.height() / pixmap.devicePixelRatioF()
        area = self.contentsRect()
        x = area.x() + (area.width() - width) / 2
        y = area.y() + (area.height() - height) / 2
        scale_x, scale_y = width / self.page_size[0], height / self.page_size[1]
        return tuple(QRectF(x + x0 * scale_x, y + y0 * scale_y, (x1 - x0) * scale_x, (y1 - y0) * scale_y)
                     for x0, y0, x1, y1 in self.highlight_rects)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        bounds = self.highlight_bounds()
        if bounds:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(157, 218, 131, 75))
            painter.setPen(QPen(QColor(60, 131, 72, 160), 1))
            for rectangle in bounds:
                painter.drawRoundedRect(rectangle.adjusted(-1, -0.5, 1, 0.5), 3, 3)
            painter.end()


class PdfViewer(QWidget):
    render_requested = Signal(int, float)
    page_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info: PdfInfo | None = None
        self.page_index = 0
        self.page_texts: dict[int, str] = {}
        self.rendered_page_index = None
        self._reading_chunk: TextChunk | None = None
        self._reading_cue: SpeechCue | None = None
        self._last_line_key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        toolbar = QHBoxLayout()
        self.previous = QPushButton()
        self.previous.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.previous.setToolTip("Previous page")
        self.previous.setAccessibleName("Previous page")
        self.next = QPushButton()
        self.next.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.next.setToolTip("Next page")
        self.next.setAccessibleName("Next page")
        self.page_number = QSpinBox()
        self.page_number.setRange(1, 1)
        self.page_number.setFixedWidth(78)
        self.page_number.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.page_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_number.setAccessibleName("Page number")
        self.page_count = QLabel("of 0")
        self.page_count.setObjectName("muted")
        self.zoom = QComboBox()
        self.zoom.addItems(["Fit width", "Fit page", "75%", "100%", "125%", "150%", "200%"])
        self.zoom.setAccessibleName("Page zoom")
        self.text_toggle = QPushButton("Text view")
        self.text_toggle.setCheckable(True)
        self.highlight_toggle = QPushButton("Highlight")
        self.highlight_toggle.setCheckable(True)
        self.highlight_toggle.setChecked(True)
        self.highlight_toggle.setToolTip("Highlight the spoken line and keep it in view")
        for widget in (self.previous, self.page_number, self.page_count, self.next):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        toolbar.addWidget(self.zoom)
        toolbar.addWidget(self.highlight_toggle)
        toolbar.addWidget(self.text_toggle)
        layout.addLayout(toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_image = PdfPageLabel("Import a PDF to start reading")
        self.page_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_image.setMinimumSize(280, 180)
        self.scroll.setWidget(self.page_image)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Extracted page text will appear here.")
        self.splitter.addWidget(self.scroll)
        self.splitter.addWidget(self.text)
        self.text.hide()
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self._request_render)
        self.previous.clicked.connect(lambda: self.page_requested.emit(self.page_index - 1))
        self.next.clicked.connect(lambda: self.page_requested.emit(self.page_index + 1))
        self.page_number.valueChanged.connect(lambda value: self.page_requested.emit(value - 1))
        self.zoom.currentTextChanged.connect(lambda _text: self.timer.start())
        self.text_toggle.toggled.connect(self._toggle_text)
        self.highlight_toggle.toggled.connect(lambda _checked: self._apply_highlight(force=True))
        self.splitter.splitterMoved.connect(lambda _position, _index: self.timer.start())
        self.set_document(None)

    def set_document(self, info: PdfInfo | None) -> None:
        self.info = info
        self.rendered_page_index = None
        self.clear_reading_highlight()
        self.page_texts.clear()
        self.text.clear()
        self.page_image.clear()
        self.page_image.setText("Opening your PDF…" if info else "Import a PDF to start reading")
        self.page_image.resize(400, 260)
        self.page_number.blockSignals(True)
        self.page_number.setRange(1, info.page_count if info else 1)
        self.page_number.setValue(1)
        self.page_number.blockSignals(False)
        self.page_count.setText(f"of {info.page_count}" if info else "of 0")
        for widget in (self.page_number, self.zoom, self.text_toggle):
            widget.setEnabled(info is not None)
        self.page_index = 0
        self.previous.setEnabled(False)
        self.next.setEnabled(bool(info and info.page_count > 1))

    def set_page(self, page_index: int) -> None:
        if not self.info:
            return
        next_index = min(max(0, page_index), self.info.page_count - 1)
        if next_index != self.page_index:
            self.rendered_page_index = None
        self.page_index = next_index
        self.page_number.blockSignals(True)
        self.page_number.setValue(self.page_index + 1)
        self.page_number.blockSignals(False)
        self.previous.setEnabled(self.page_index > 0)
        self.next.setEnabled(self.page_index < self.info.page_count - 1)
        self.text.setPlainText(self.page_texts.get(self.page_index, ""))
        self.scroll.verticalScrollBar().setValue(0)
        self._apply_highlight(force=True)
        self.timer.start()

    def set_texts(self, pages: list[tuple[int, str]]) -> None:
        self.page_texts = dict(pages)
        self.text.setPlainText(self.page_texts.get(self.page_index, ""))
        self._apply_highlight(force=True)

    def _toggle_text(self, enabled: bool) -> None:
        self.text.setVisible(enabled)
        self._apply_highlight(force=True)
        self.timer.start()

    def _request_render(self) -> None:
        if not self.info:
            return
        width, height = self.info.page_sizes[self.page_index]
        mode = self.zoom.currentText()
        fit_width = max(100, self.scroll.viewport().width() - 30) / max(1, width)
        if mode == "Fit width":
            scale = fit_width
        elif mode == "Fit page":
            scale = min(fit_width, max(100, self.scroll.viewport().height() - 26) / max(1, height))
        else:
            scale = int(mode.rstrip("%")) / 100
        self.render_requested.emit(self.page_index, round(scale * self.devicePixelRatioF(), 3))

    def show_render(self, page: RenderedPage) -> None:
        if page.page_index != self.page_index:
            return
        image = QImage(page.samples, page.width, page.height, page.stride, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        self.page_image.setPixmap(pixmap)
        self.page_image.adjustSize()
        self.rendered_page_index = page.page_index
        self._apply_highlight(force=True)

    def set_reading_highlight(self, chunk: TextChunk, cue: SpeechCue) -> None:
        self._reading_chunk, self._reading_cue = chunk, cue
        self._apply_highlight()

    def clear_reading_highlight(self) -> None:
        self._reading_chunk = self._reading_cue = None
        self._last_line_key = None
        self.page_image.set_highlights((), (1.0, 1.0))
        self.text.setExtraSelections([])

    def _apply_highlight(self, force: bool = False) -> None:
        chunk, cue = self._reading_chunk, self._reading_cue
        lines = []
        if self.highlight_toggle.isChecked() and self.info and chunk and cue and chunk.page_index == self.page_index:
            lines = [line for line in chunk.lines if line.start < cue.text_end and line.end > cue.text_start]
        key = (self.page_index, tuple(lines))
        if key == self._last_line_key and not force:
            return
        self._last_line_key = key
        rectangles = [line.rect for line in lines] if self.rendered_page_index == self.page_index else []
        page_size = self.info.page_sizes[self.page_index] if self.info else (1.0, 1.0)
        self.page_image.set_highlights(rectangles, page_size)
        selections = []
        text = self.page_texts.get(self.page_index, "")
        for line in lines:
            if line.page_end > len(text):
                continue
            # QTextCursor counts UTF-16 units; Python indexes Unicode characters.
            start = len(text[:line.page_start].encode("utf-16-le")) // 2
            end = len(text[:line.page_end].encode("utf-16-le")) // 2
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.text.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            selection.format.setBackground(QColor("#375d43"))
            selections.append(selection)
        self.text.setExtraSelections(selections)
        if selections and self.text.isVisible():
            cursor = QTextCursor(selections[0].cursor)
            cursor.clearSelection()
            self.text.setTextCursor(cursor)
            self.text.ensureCursorVisible()
        bounds = self.page_image.highlight_bounds()
        if bounds:
            center = bounds[0].center()
            self.scroll.ensureVisible(round(center.x()), round(center.y()), 30, 80)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        orientation = Qt.Orientation.Vertical if self.width() < 850 else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
        self.timer.start()

