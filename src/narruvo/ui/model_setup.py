"""First-run voice setup, including cancellable I/O in a QThread."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout

from narruvo.config import AppPaths
from narruvo.models import DownloadCancelled, RELEASE_URL, download_models


class DownloadThread(QThread):
    progress = Signal(int, int, str)
    success = Signal(object)
    failure = Signal(str)
    cancelled = Signal()

    def __init__(self, directory: Path, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.cancel = Event()

    def run(self) -> None:
        try:
            result = download_models(self.directory, self.progress.emit, self.cancel)
            self.success.emit(result)
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failure.emit(str(exc))


class ModelSetupDialog(QDialog):
    files_selected = Signal(str, str)

    def __init__(self, paths: AppPaths, model: Path, voices: Path, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.thread: DownloadThread | None = None
        self.setWindowTitle("Narruvo · Set up offline voices")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(16)
        title = QLabel("Bring your books to life")
        title.setObjectName("title")
        layout.addWidget(title)
        description = QLabel("Kokoro runs entirely on your computer using the CPU. Download the official English model and voices once (~354 MB), then listen offline. No account or API key is needed.\n\nYou can skip setup and continue viewing PDFs.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.download = QPushButton("Download official files · 354 MB")
        self.download.setObjectName("accent")
        self.download.clicked.connect(self._download)
        layout.addWidget(self.download)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.message = QLabel(f"Files will be stored in {paths.models}")
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        layout.addWidget(self.message)
        source = QPushButton("View official model source ↗")
        source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASE_URL)))
        layout.addWidget(source)
        layout.addWidget(QLabel("Or select existing model files"))
        self.model_field = QLineEdit(str(model) if model.is_file() else "")
        self.voices_field = QLineEdit(str(voices) if voices.is_file() else "")
        self.model_field.setPlaceholderText("Kokoro .onnx model")
        self.voices_field.setPlaceholderText("voices-v1.0.bin")
        self.browse_buttons = []
        for field, label, pattern in ((self.model_field, "Model", "ONNX model (*.onnx)"), (self.voices_field, "Voices", "Voice file (*.bin *.npz)")):
            row = QHBoxLayout()
            row.addWidget(field, 1)
            button = QPushButton(f"Browse {label.lower()}…")
            button.clicked.connect(lambda _checked=False, f=field, p=pattern: self._browse(f, p))
            self.browse_buttons.append(button)
            row.addWidget(button)
            layout.addLayout(row)
        footer = QHBoxLayout()
        self.skip = QPushButton("Set up later")
        self.skip.clicked.connect(self.reject)
        self.use = QPushButton("Use selected files")
        self.use.clicked.connect(self._use_files)
        footer.addWidget(self.skip)
        footer.addStretch()
        footer.addWidget(self.use)
        layout.addLayout(footer)

    def _browse(self, field: QLineEdit, pattern: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Select Kokoro file", "", pattern)
        if filename:
            field.setText(filename)

    def _use_files(self) -> None:
        model, voices = Path(self.model_field.text()), Path(self.voices_field.text())
        if not model.is_file() or not voices.is_file():
            self.message.setText("Select both an existing ONNX model and a voice file.")
            return
        self.files_selected.emit(str(model.resolve()), str(voices.resolve()))
        self.accept()

    def _download(self) -> None:
        if self.thread and self.thread.isRunning():
            self.thread.cancel.set()
            self.download.setEnabled(False)
            self.message.setText("Cancelling… waiting for the current network read to finish.")
            return
        self.download.setText("Cancel download")
        self.skip.setEnabled(False)
        self.use.setEnabled(False)
        for widget in (*self.browse_buttons, self.model_field, self.voices_field):
            widget.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.thread = DownloadThread(self.paths.models, self)
        self.thread.progress.connect(self._progress)
        self.thread.success.connect(self._success)
        self.thread.failure.connect(lambda message: self.message.setText(f"Download failed: {message}\nCheck your connection, retry, or select existing files."))
        self.thread.cancelled.connect(lambda: self.message.setText("Download cancelled. Verified files are retained; you can retry at any time."))
        self.thread.finished.connect(self._finished)
        self.thread.start()

    def _progress(self, done: int, total: int, name: str) -> None:
        self.progress.setValue(round(done / total * 100))
        self.message.setText(f"{name} · {done / 1_000_000:.1f} / {total / 1_000_000:.1f} MB")

    def _success(self, paths: tuple[Path, ...]) -> None:
        self.model_field.setText(str(paths[0]))
        self.voices_field.setText(str(paths[1]))
        self.message.setText("Files downloaded and checksums verified. Select Use selected files to load the voices.")
        self.progress.setValue(100)

    def _finished(self) -> None:
        self.download.setText("Download / verify official files · 354 MB")
        self.download.setEnabled(True)
        self.skip.setEnabled(True)
        self.use.setEnabled(True)
        for widget in (*self.browse_buttons, self.model_field, self.voices_field):
            widget.setEnabled(True)

    def reject(self) -> None:
        if self.thread and self.thread.isRunning():
            self.thread.cancel.set()
            self.message.setText("Cancelling download… this dialog can close once the current network read ends.")
            return
        super().reject()
