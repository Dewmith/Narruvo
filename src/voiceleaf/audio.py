"""Small Qt Multimedia adapter. All calls belong to the GUI thread."""

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    ready = Signal()
    ended = Signal()
    failed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.loading = False
        self.pending_position = 0
        self.allow_end = False
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda _code, message: self.failed.emit(f"Audio playback failed: {message}"))
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda value: self.duration_changed.emit(value))

    @property
    def seekable(self) -> bool:
        return self.player.isSeekable()

    def load(self, path: str, position_ms: int = 0) -> None:
        self.allow_end = False
        self.loading = True
        self.pending_position = max(0, position_ms)
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))

    def _status(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia) and self.loading:
            self.loading = False
            self.allow_end = True
            if self.pending_position and self.seekable:
                self.player.setPosition(min(self.pending_position, max(0, self.player.duration() - 1)))
            self.ready.emit()
            self.position_changed.emit(self.player.position())
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self.allow_end:
            self.allow_end = False
            self.ended.emit()

    def _position(self, position: int) -> None:
        if not self.loading:
            self.position_changed.emit(position)

    def play(self) -> None:
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def stop(self, unload: bool = False) -> None:
        self.allow_end = False
        self.loading = False
        self.player.stop()
        if unload:
            self.player.setSource(QUrl())

    def seek(self, position_ms: int) -> None:
        if self.seekable:
            self.player.setPosition(max(0, min(position_ms, self.player.duration())))

    def set_volume(self, volume: float) -> None:
        self.output.setVolume(max(0.0, min(1.0, volume)))

