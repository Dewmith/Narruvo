"""VoiceLeaf's desktop shell; services own processing and narration behavior."""

import logging
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from voiceleaf.config import AppPaths, Settings
from voiceleaf.documents import DocumentController
from voiceleaf.domain import PdfInfo, ReadingProgress
from voiceleaf.persistence import Library
from voiceleaf.playback import PlaybackController
from voiceleaf.ui.library_view import LibraryView
from voiceleaf.ui.model_setup import ModelSetupDialog
from voiceleaf.ui.playback_bar import PlaybackBar
from voiceleaf.ui.theme import leaf_icon
from voiceleaf.ui.viewer import PdfViewer

log = logging.getLogger(__name__)


class VoiceLeafWindow(QMainWindow):
    def __init__(self, paths: AppPaths, settings: Settings, initial_pdf: str | None = None, show_setup: bool = True):
        super().__init__()
        self.paths, self.settings = paths, settings
        self.library = Library(paths.database)
        self.documents = DocumentController(paths.root, self)
        self.playback = PlaybackController(paths.root, self)
        self.current_info: PdfInfo | None = None
        self.restored_progress = ReadingProgress()
        self.current_page = 0
        self.text_ready = False
        self.navigated_during_extraction = False
        self.setup_dialog: ModelSetupDialog | None = None
        self.error_dialog: QMessageBox | None = None
        self.closed = False
        self.setWindowTitle("VoiceLeaf · Offline PDF audiobook reader")
        self.setWindowIcon(leaf_icon())
        self.setMinimumSize(800, 600)
        self.resize(1280, 880)
        self.setAcceptDrops(True)
        self._build_ui()
        self._connect()
        self.playback.preferred_voice = settings.voice
        self.playback.active_voice = settings.voice
        self.playback.preferred_rate = settings.rate
        self.playback.active_rate = settings.rate
        self.playback.audio.set_volume(settings.volume)
        self.bar.volume.setValue(round(settings.volume * 100))
        self._refresh_library()
        self._refresh()
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(5000)
        self.save_timer.timeout.connect(self.save_progress)
        self.save_timer.start()
        self._shortcuts()
        QTimer.singleShot(0, lambda: self._startup(initial_pdf, show_setup))

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(222)
        side = QVBoxLayout(self.sidebar)
        self.sidebar_layout = side
        side.setContentsMargins(18, 24, 18, 20)
        side.setSpacing(12)
        brand_row = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(34, 34)
        logo.setPixmap(leaf_icon().pixmap(34, 34))
        brand_row.addWidget(logo)
        self.brand = QLabel("VoiceLeaf")
        self.brand.setObjectName("brand")
        brand_row.addWidget(self.brand)
        brand_row.addStretch()
        side.addLayout(brand_row)
        self.tagline = QLabel("A little more time for books.")
        self.tagline.setObjectName("muted")
        side.addWidget(self.tagline)
        side.addSpacing(22)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons = []
        for index, label in enumerate(("Library", "Currently reading", "Settings")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, i=index: self.show_panel(i))
            self.nav.addButton(button, index)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addSpacing(22)
        self.recent_label = QLabel("RECENTLY OPENED")
        self.recent_label.setObjectName("eyebrow")
        side.addWidget(self.recent_label)
        self.recents = QListWidget()
        self.recents.setWordWrap(True)
        self.recents.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.recents.itemClicked.connect(lambda item: self.open_library(item.data(Qt.ItemDataRole.UserRole)))
        side.addWidget(self.recents, 1)
        self.compact_spacer = QWidget()
        self.compact_spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.compact_spacer.hide()
        side.addWidget(self.compact_spacer, 1)
        self.import_button = QPushButton("Import PDF…")
        self.import_button.setObjectName("accent")
        self.import_button.setToolTip("Import PDF (Ctrl+O)")
        self.import_button.clicked.connect(self.import_pdf)
        side.addWidget(self.import_button)
        self.local_label = QLabel("LOCAL BY DESIGN\nNo accounts. No uploads.")
        self.local_label.setObjectName("muted")
        side.addWidget(self.local_label)
        root_layout.addWidget(self.sidebar)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        self.body_layout = body_layout
        body_layout.setContentsMargins(26, 24, 26, 18)
        body_layout.setSpacing(14)
        self.stack = QStackedWidget()
        self.library_view = LibraryView()
        self.stack.addWidget(self.library_view)
        reader = QWidget()
        reader_layout = QVBoxLayout(reader)
        reader_layout.setContentsMargins(0, 0, 0, 0)
        reader_layout.setSpacing(10)
        eyebrow = QLabel("CURRENTLY READING")
        eyebrow.setObjectName("eyebrow")
        reader_layout.addWidget(eyebrow)
        self.document_title = QLabel("Make room for a good book")
        self.document_title.setObjectName("title")
        self.document_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        reader_layout.addWidget(self.document_title)
        self.reader_notice = QLabel("Import a PDF from your computer, or choose a book from your library.")
        self.reader_notice.setObjectName("muted")
        self.reader_notice.setWordWrap(True)
        reader_layout.addWidget(self.reader_notice)
        self.extraction = QProgressBar()
        self.extraction.setMaximumHeight(22)
        self.extraction.hide()
        reader_layout.addWidget(self.extraction)
        self.viewer = PdfViewer()
        reader_layout.addWidget(self.viewer, 1)
        self.stack.addWidget(reader)
        self.stack.addWidget(self._settings_panel())
        body_layout.addWidget(self.stack, 1)
        self.status_label = QLabel("Welcome to VoiceLeaf · import a PDF to begin")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        body_layout.addWidget(self.status_label)
        self.bar = PlaybackBar()
        body_layout.addWidget(self.bar)
        root_layout.addWidget(body, 1)
        self.show_panel(0)

    def _settings_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        title = QLabel("Make yourself comfortable")
        title.setObjectName("title")
        layout.addWidget(title)
        description = QLabel("Your reading preferences follow each document. Voice and speed changes take effect at the next section.")
        description.setWordWrap(True)
        description.setObjectName("muted")
        layout.addWidget(description)
        model_title = QLabel("Offline voices")
        model_title.setStyleSheet("font-size: 17px; font-weight: 600;")
        layout.addWidget(model_title)
        self.model_status = QLabel("Models have not been loaded yet.")
        self.model_status.setWordWrap(True)
        layout.addWidget(self.model_status)
        setup = QPushButton("Set up voices / select model files…")
        setup.setObjectName("accent")
        setup.clicked.connect(self.open_setup)
        layout.addWidget(setup, alignment=Qt.AlignmentFlag.AlignLeft)
        storage = QLabel(f"Local storage\n{self.paths.root}\n\nGenerated audio is reused and limited to 2 GB. Original PDFs stay in their existing locations.")
        storage.setObjectName("muted")
        storage.setWordWrap(True)
        layout.addWidget(storage)
        buttons = QHBoxLayout()
        clear = QPushButton("Clear generated audio")
        clear.clicked.connect(self.playback.clear_cache)
        open_folder = QPushButton("Open data folder")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.root))))
        buttons.addWidget(clear)
        buttons.addWidget(open_folder)
        buttons.addStretch()
        layout.addLayout(buttons)
        tips = QLabel("Keyboard shortcuts\nCtrl+O  Import PDF     Space  Play / pause\nCtrl+Left / Ctrl+Right  Previous / next section\nCtrl+L  Library     Ctrl+,  Settings\n\nPDFs with complex layouts may need a quick check in Text view. Image-only PDFs need OCR, which is planned for a later release.")
        tips.setObjectName("muted")
        tips.setWordWrap(True)
        layout.addWidget(tips)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        return scroll

    def _connect(self) -> None:
        self.library_view.import_requested.connect(self.import_pdf)
        self.library_view.open_requested.connect(self.open_library)
        self.library_view.remove_requested.connect(self.remove_document)
        self.library_view.locate_requested.connect(self.locate_document)
        self.documents.opened.connect(self._opened)
        self.documents.rendered.connect(self.viewer.show_render)
        self.documents.text_ready.connect(self._text_ready)
        self.documents.extraction_progress.connect(self._extraction_progress)
        self.documents.error.connect(self.show_error)
        self.viewer.render_requested.connect(self.documents.render)
        self.viewer.page_requested.connect(self.navigate_page)
        self.playback.changed.connect(self._refresh)
        self.playback.status.connect(self.status_label.setText)
        self.playback.error.connect(self.show_error)
        self.playback.voices_changed.connect(self._voices_changed)
        self.playback.page_changed.connect(self._follow_page)
        self.playback.setup_requested.connect(self.open_setup)
        self.playback.checkpoint.connect(self.save_progress)
        self.bar.play_clicked.connect(self.playback.toggle)
        self.bar.stop_clicked.connect(self.playback.stop)
        self.bar.previous_clicked.connect(self.playback.previous)
        self.bar.next_clicked.connect(self.playback.next)
        self.bar.seek_requested.connect(self.playback.seek)
        self.bar.preference_changed.connect(self._preferences)
        self.bar.volume_changed.connect(self._volume)
        self.bar.setup_requested.connect(self.open_setup)

    def _shortcuts(self) -> None:
        for sequence, callback in (("Ctrl+O", self.import_pdf), ("Ctrl+L", lambda: self.show_panel(0)), ("Ctrl+,", lambda: self.show_panel(2)), ("Ctrl+Right", self.playback.next), ("Ctrl+Left", self.playback.previous), ("Space", self._space)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)

    def _space(self) -> None:
        if not isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)):
            self.playback.toggle()

    def _startup(self, initial_pdf: str | None, show_setup: bool) -> None:
        if self.closed:
            return
        model, voices = self.settings.model_files(self.paths)
        if model.is_file() and voices.is_file():
            self.playback.initialize_models(model, voices)
        elif show_setup and not self.settings.setup_dismissed:
            QTimer.singleShot(300, self.open_setup)
        if initial_pdf:
            self.open_pdf(initial_pdf)
        elif self.settings.last_document_id:
            last = self.library.get(self.settings.last_document_id)
            if last and Path(last.path).is_file():
                self.open_pdf(last.path)

    def show_panel(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        if index == 0 and hasattr(self, "library_view"):
            self._refresh_library()

    def import_pdf(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Import a PDF", "", "PDF documents (*.pdf)")
        if filename:
            self.open_pdf(filename)

    def open_pdf(self, filename: str) -> None:
        self.save_progress()
        self.current_info = None
        self.text_ready = False
        self.navigated_during_extraction = False
        self.playback.load([], ReadingProgress(preferred_voice=self.settings.voice, active_voice=self.settings.voice, preferred_rate=self.settings.rate, active_rate=self.settings.rate))
        self.viewer.set_document(None)
        self.document_title.setText("Opening your PDF…")
        self.reader_notice.setText("Pages will appear while the document is prepared for narration.")
        self.reader_notice.show()
        self.status_label.setText(f"Opening {Path(filename).name}…")
        self.extraction.setRange(0, 0)
        self.extraction.show()
        self.show_panel(1)
        self.documents.open(filename)

    def open_library(self, document_id: str) -> None:
        record = self.library.get(document_id)
        if not record:
            return
        if Path(record.path).is_file():
            self.open_pdf(record.path)
            return
        message = QMessageBox(self)
        message.setWindowTitle("PDF not found")
        message.setText("This PDF has moved or is unavailable.")
        message.setInformativeText(record.path)
        locate = message.addButton("Locate PDF…", QMessageBox.ButtonRole.AcceptRole)
        remove = message.addButton("Remove entry", QMessageBox.ButtonRole.DestructiveRole)
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        if message.clickedButton() == locate:
            self.locate_document(document_id)
        elif message.clickedButton() == remove:
            self.remove_document(document_id)

    def locate_document(self, document_id: str) -> None:
        record = self.library.get(document_id)
        filename, _ = QFileDialog.getOpenFileName(self, "Locate the original PDF", str(Path(record.path).parent) if record else "", "PDF documents (*.pdf)")
        if filename:
            self.open_pdf(filename)

    def remove_document(self, document_id: str) -> None:
        if self.current_info and self.current_info.document_id == document_id:
            self.current_info = None
            self.text_ready = False
            self.playback.load([], ReadingProgress())
            self.documents.unload()
            self.viewer.set_document(None)
            self.document_title.setText("Make room for a good book")
            self.reader_notice.setText("Choose another PDF from your library.")
            self.reader_notice.show()
        self.library.remove(document_id)
        if self.settings.last_document_id == document_id:
            self.settings.last_document_id = ""
            self._save_settings()
        self._refresh_library()
        self.show_panel(0)

    def _opened(self, info: PdfInfo) -> None:
        defaults = ReadingProgress(active_voice=self.settings.voice, preferred_voice=self.settings.voice, active_rate=self.settings.rate, preferred_rate=self.settings.rate)
        self.restored_progress = self.library.upsert(info, defaults)
        self.current_info = info
        self.settings.last_document_id = info.document_id
        self._save_settings()
        self.current_page = min(max(0, self.restored_progress.view_page), info.page_count - 1)
        self.document_title.setText(info.title)
        self.document_title.setToolTip(info.title)
        self.setWindowTitle(f"{info.title} · VoiceLeaf")
        self.viewer.set_document(info)
        self.viewer.set_page(self.current_page)
        self.viewer.timer.stop()
        self.viewer._request_render()
        self._refresh_library()
        self._refresh()

    def _extraction_progress(self, completed: int, total: int) -> None:
        self.extraction.setRange(0, total)
        self.extraction.setValue(completed)
        self.extraction.setFormat(f"Preparing narration · {completed} / {total} pages")

    def _text_ready(self, pages, chunks) -> None:
        if not self.current_info:
            return
        self.viewer.set_texts(pages)
        self.playback.load(chunks, self.restored_progress)
        if self.navigated_during_extraction:
            self.playback.navigate_page(self.current_page)
        self.text_ready = True
        self.extraction.hide()
        if not chunks:
            self.reader_notice.setText("This PDF has no extractable reading text. It may be scanned or image-only. You can view its pages; OCR support is planned for a later release.")
            self.reader_notice.show()
        elif sum(bool(text.strip()) for _, text in pages) < len(pages) / 2:
            self.reader_notice.setText("Several pages contain little or no text. Image-only pages are skipped during narration. OCR support is planned for a later release.")
            self.reader_notice.show()
        elif sum(sum(char.isalpha() for char in text) for _, text in pages) < 40:
            self.reader_notice.setText("Very little reading text was found. If this is a scanned PDF, OCR is needed to read the images; OCR support is planned for a later release.")
            self.reader_notice.show()
        else:
            self.reader_notice.hide()
        self.status_label.setText(f"Ready · {len(chunks)} readable sections" if chunks else "Viewing only · OCR is needed for narration")
        self._refresh()

    def navigate_page(self, page: int) -> None:
        if not self.current_info:
            return
        page = min(max(0, page), self.current_info.page_count - 1)
        self.playback.navigate_page(page)
        self.current_page = page
        if not self.text_ready:
            self.navigated_during_extraction = True
            self.restored_progress.view_page = page
        self.viewer.set_page(page)
        self.save_progress()

    def _follow_page(self, page: int) -> None:
        self.current_page = page
        if self.viewer.page_index != page:
            self.viewer.set_page(page)

    def _preferences(self, voice: str, rate: float) -> None:
        self.settings.voice, self.settings.rate = voice, rate
        self.playback.set_preferences(voice, rate)
        self._save_settings()

    def _volume(self, volume: float) -> None:
        self.settings.volume = volume
        self.playback.audio.set_volume(volume)
        self._save_settings()

    def _voices_changed(self, voices: list[str]) -> None:
        self.bar.set_voices(voices, self.playback.preferred_voice)

    def _refresh(self) -> None:
        if not hasattr(self, "bar"):
            return
        self.bar.refresh(self.playback, self.current_info.title if self.current_info else None)
        cue = self.playback.reading_cue
        if cue is not None and self.playback.chunks:
            self.viewer.set_reading_highlight(self.playback.chunks[self.playback.index], cue)
        else:
            self.viewer.clear_reading_highlight()
        self.model_status.setText(f"{len(self.playback.voices)} English voices available · CPU inference · offline" if self.playback.ready else "Voices are loading…" if self.playback.init_job is not None else "Set up Kokoro model files to enable narration. PDF viewing works without them.")

    def _refresh_library(self) -> None:
        records = self.library.recent()
        self.library_view.update_documents(records)
        self.recents.clear()
        for record in records[:8]:
            item = QListWidgetItem(record.title)
            item.setData(Qt.ItemDataRole.UserRole, record.document_id)
            item.setToolTip(record.path)
            self.recents.addItem(item)

    def save_progress(self) -> None:
        if not self.current_info or self.closed:
            return
        try:
            progress = self.playback.snapshot(self.current_page) if self.text_ready else self.restored_progress
            progress.view_page = self.current_page
            self.library.save_progress(self.current_info.document_id, progress)
        except Exception:
            log.exception("Could not save reading progress")
            self.status_label.setText("Reading progress could not be saved. Check the data folder and logs.")

    def _save_settings(self) -> None:
        try:
            self.settings.save(self.paths.settings_file)
        except OSError:
            log.exception("Could not save settings")
            self.status_label.setText("Settings could not be saved. Check the data folder and logs.")

    def open_setup(self) -> None:
        if self.closed:
            return
        if self.setup_dialog:
            self.setup_dialog.raise_()
            self.setup_dialog.activateWindow()
            return
        model, voices = self.settings.model_files(self.paths)
        self.setup_dialog = ModelSetupDialog(self.paths, model, voices, self)
        self.setup_dialog.files_selected.connect(self._model_selected)
        self.setup_dialog.finished.connect(self._setup_finished)
        self.setup_dialog.open()

    def _model_selected(self, model: str, voices: str) -> None:
        self.settings.model_path, self.settings.voices_path = model, voices
        self.settings.setup_dismissed = False
        self._save_settings()
        self.playback.initialize_models(Path(model), Path(voices))

    def _setup_finished(self, result: int) -> None:
        if result == 0:
            self.settings.setup_dismissed = True
            self._save_settings()
        if self.setup_dialog:
            self.setup_dialog.deleteLater()
        self.setup_dialog = None

    def show_error(self, message: str) -> None:
        log.error("Application error: %s", message)
        self.status_label.setText(message.splitlines()[0])
        self.extraction.hide()
        if self.error_dialog and self.error_dialog.isVisible():
            self.error_dialog.setInformativeText(message)
            return
        self.error_dialog = QMessageBox(QMessageBox.Icon.Warning, "VoiceLeaf", message, QMessageBox.StandardButton.Ok, self)
        self.error_dialog.setTextFormat(Qt.TextFormat.PlainText)
        self.error_dialog.open()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "sidebar"):
            return
        compact = self.width() < 1120
        self.sidebar.setFixedWidth(78 if compact else 222)
        self.sidebar_layout.setContentsMargins(10 if compact else 18, 24, 10 if compact else 18, 20)
        self.compact_spacer.setVisible(compact)
        for widget in (self.brand, self.tagline, self.recent_label, self.recents, self.local_label):
            widget.setVisible(not compact)
        for button, label, short in zip(self.nav_buttons, ("Library", "Currently reading", "Settings"), ("Lib", "Read", "Set")):
            button.setText(short if compact else label)
        self.import_button.setText("+" if compact else "Import PDF…")
        self.body_layout.setContentsMargins(16 if compact else 26, 18, 16 if compact else 26, 16)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf") for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.open_pdf(url.toLocalFile())
                event.acceptProposedAction()
                break

    def closeEvent(self, event) -> None:
        if self.closed:
            event.accept()
            return
        if self.setup_dialog and self.setup_dialog.thread and self.setup_dialog.thread.isRunning():
            self.setup_dialog.thread.cancel.set()
            self.setup_dialog.thread.finished.connect(self.close)
            self.status_label.setText("Cancelling the model download before closing…")
            event.ignore()
            return
        self.save_timer.stop()
        self.viewer.timer.stop()
        self.save_progress()
        self._save_settings()
        self.closed = True
        self.documents.close()
        self.playback.close()
        self.library.close()
        event.accept()

