"""A single-page raster PDF viewer with responsive layout and a text pane."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStyle, QVBoxLayout, QWidget

from voiceleaf.domain import PdfInfo
from voiceleaf.pdf import RenderedPage


class PdfViewer(QWidget):
    render_requested = Signal(int, float)
    page_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info: PdfInfo | None = None
        self.page_index = 0
        self.page_texts: dict[int, str] = {}
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
        for widget in (self.previous, self.page_number, self.page_count, self.next):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        toolbar.addWidget(self.zoom)
        toolbar.addWidget(self.text_toggle)
        layout.addLayout(toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_image = QLabel("Import a PDF to start reading")
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
        self.splitter.splitterMoved.connect(lambda _position, _index: self.timer.start())
        self.set_document(None)

    def set_document(self, info: PdfInfo | None) -> None:
        self.info = info
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
        self.page_index = min(max(0, page_index), self.info.page_count - 1)
        self.page_number.blockSignals(True)
        self.page_number.setValue(self.page_index + 1)
        self.page_number.blockSignals(False)
        self.previous.setEnabled(self.page_index > 0)
        self.next.setEnabled(self.page_index < self.info.page_count - 1)
        self.text.setPlainText(self.page_texts.get(self.page_index, ""))
        self.scroll.verticalScrollBar().setValue(0)
        self.timer.start()

    def set_texts(self, pages: list[tuple[int, str]]) -> None:
        self.page_texts = dict(pages)
        self.text.setPlainText(self.page_texts.get(self.page_index, ""))

    def _toggle_text(self, enabled: bool) -> None:
        self.text.setVisible(enabled)
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        orientation = Qt.Orientation.Vertical if self.width() < 850 else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
        self.timer.start()

