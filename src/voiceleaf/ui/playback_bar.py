from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QStyle, QWidget


def timestamp(milliseconds: int) -> str:
    seconds = max(0, milliseconds) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def voice_label(key: str) -> str:
    name = key.partition("_")[2].replace("_", " ").title()
    accent = "British" if key.startswith("b") else "American"
    return f"{name} · {accent}"


class PlaybackBar(QFrame):
    play_clicked = Signal()
    stop_clicked = Signal()
    previous_clicked = Signal()
    next_clicked = Signal()
    seek_requested = Signal(int)
    preference_changed = Signal(str, float)
    volume_changed = Signal(float)
    setup_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("playback")
        grid = QGridLayout(self)
        self.grid = grid
        grid.setContentsMargins(18, 12, 18, 14)
        grid.setVerticalSpacing(10)
        self.title = QLabel("Your next good listen")
        self.title.setStyleSheet("font-weight: 600;")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.section = QLabel("Import a PDF to begin")
        self.section.setObjectName("muted")
        grid.addWidget(self.title, 0, 0)
        grid.addWidget(self.section, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)
        controls = QHBoxLayout()
        self.previous = self._button("", QStyle.StandardPixmap.SP_MediaSkipBackward, "Previous section")
        self.play = self._button("Play", QStyle.StandardPixmap.SP_MediaPlay, "Play / pause (Space)")
        self.play.setObjectName("accent")
        self.play.setMinimumWidth(92)
        self.stop = self._button("", QStyle.StandardPixmap.SP_MediaStop, "Stop and restart this section")
        self.next = self._button("", QStyle.StandardPixmap.SP_MediaSkipForward, "Next section")
        for widget in (self.previous, self.play, self.stop, self.next):
            controls.addWidget(widget)
        self.controls_widget = QWidget()
        self.controls_widget.setObjectName("playerGroup")
        self.controls_widget.setLayout(controls)
        controls.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.controls_widget, 1, 0)
        seek_row = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Position within the current section")
        self.seek.setTracking(False)
        self.seek.setMinimumWidth(90)
        self.time = QLabel("0:00 / 0:00")
        self.time.setObjectName("muted")
        self.time.setMinimumWidth(92)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.time)
        grid.addLayout(seek_row, 1, 1)
        self.voice_row = QWidget()
        self.voice_row.setObjectName("playerGroup")
        voice_layout = QHBoxLayout(self.voice_row)
        voice_layout.setContentsMargins(0, 0, 0, 0)
        voice_layout.addWidget(QLabel("Voice"))
        self.voice = QComboBox()
        self.voice.setMinimumWidth(160)
        self.voice.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.voice.setAccessibleName("Narration voice")
        self.voice.addItem("Set up offline voices…", None)
        voice_layout.addWidget(self.voice, 1)
        grid.addWidget(self.voice_row, 2, 0)
        self.options = QWidget()
        self.options.setObjectName("playerGroup")
        options = QHBoxLayout(self.options)
        options.setContentsMargins(0, 0, 0, 0)
        options.addWidget(QLabel("Speed"))
        self.rate = QDoubleSpinBox()
        self.rate.setRange(0.5, 2.0)
        self.rate.setSingleStep(0.05)
        self.rate.setDecimals(2)
        self.rate.setValue(1.0)
        self.rate.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.rate.setSuffix(" ×")
        self.rate.setToolTip("Changes apply to the next section")
        self.rate.setAccessibleName("Narration speed, applied at the next section")
        options.addWidget(self.rate)
        options.addStretch()
        options.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(90)
        self.volume.setAccessibleName("Playback volume")
        options.addWidget(self.volume)
        grid.addWidget(self.options, 2, 1)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 3)
        self.previous.clicked.connect(self.previous_clicked)
        self.play.clicked.connect(self.play_clicked)
        self.stop.clicked.connect(self.stop_clicked)
        self.next.clicked.connect(self.next_clicked)
        self.seek.sliderReleased.connect(lambda: self.seek_requested.emit(self.seek.value()))
        self.voice.activated.connect(self._preferences)
        self.rate.valueChanged.connect(self._preferences)
        self.volume.valueChanged.connect(lambda value: self.volume_changed.emit(value / 100))

    def _button(self, text, icon, description):
        button = QPushButton(text)
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(description)
        button.setAccessibleName(description)
        return button

    def _preferences(self, *_args) -> None:
        voice = self.voice.currentData()
        if voice is None:
            self.setup_requested.emit()
        else:
            self.preference_changed.emit(voice, self.rate.value())

    def set_voices(self, voices: list[str], preferred: str) -> None:
        self.voice.blockSignals(True)
        self.voice.clear()
        for key in voices:
            self.voice.addItem(voice_label(key), key)
        if not voices:
            self.voice.addItem("Set up offline voices…", None)
        index = self.voice.findData(preferred)
        self.voice.setCurrentIndex(max(0, index))
        self.voice.blockSignals(False)

    def refresh(self, playback, title: str | None) -> None:
        self.title.setText(title or "Your next good listen")
        self.title.setToolTip(title or "")
        has_text = bool(playback.chunks)
        self.play.setEnabled(has_text)
        self.stop.setEnabled(has_text)
        self.previous.setEnabled(has_text and playback.index > 0)
        self.next.setEnabled(has_text and playback.index + 1 < len(playback.chunks))
        playing = playback.intent == "play"
        self.play.setText("Pause" if playing else "Play")
        self.play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay))
        if has_text:
            chunk = playback.chunks[playback.index]
            self.section.setText(f"Page {chunk.page_index + 1} · Section {playback.index + 1} / {len(playback.chunks)}")
        else:
            self.section.setText("No readable sections" if title else "Import a PDF to begin")
        self.seek.setEnabled(bool(playback.current_audio and playback.audio.seekable))
        if not self.seek.isSliderDown():
            self.seek.setRange(0, max(1, playback.duration_ms))
            self.seek.setValue(playback.position_ms)
        self.time.setText(f"{timestamp(playback.position_ms)} / {timestamp(playback.duration_ms)}")
        self.rate.blockSignals(True)
        self.rate.setValue(playback.preferred_rate)
        self.rate.blockSignals(False)
        index = self.voice.findData(playback.preferred_voice)
        if index >= 0 and index != self.voice.currentIndex():
            self.voice.blockSignals(True)
            self.voice.setCurrentIndex(index)
            self.voice.blockSignals(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 760
        desired_row = 3 if compact else 2
        if self.grid.indexOf(self.options) >= 0 and self.grid.getItemPosition(self.grid.indexOf(self.options))[0] != desired_row:
            self.grid.removeWidget(self.options)
            self.grid.removeWidget(self.voice_row)
            self.grid.addWidget(self.voice_row, 2, 0, 1, 2 if compact else 1)
            self.grid.addWidget(self.options, desired_row, 0 if compact else 1, 1, 2 if compact else 1)

