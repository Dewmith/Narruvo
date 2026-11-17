"""Narration state machine: bounded prefetch, intent preservation, stale-job rejection."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from voiceleaf.audio import AudioPlayer
from voiceleaf.domain import AudioResult, ReadingProgress, SynthesisRequest, TextChunk
from voiceleaf.workers import ProcessWorker


class PlaybackController(QObject):
    changed = Signal()
    status = Signal(str)
    error = Signal(str)
    page_changed = Signal(int)
    voices_changed = Signal(object)
    setup_requested = Signal()
    checkpoint = Signal()

    def __init__(self, data_root: Path, parent=None, worker=None, audio=None):
        super().__init__(parent)
        self.worker = worker or ProcessWorker("tts", data_root, self)
        self.audio = audio or AudioPlayer(self)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._failed)
        self.audio.ready.connect(self._audio_ready)
        self.audio.ended.connect(self._ended)
        self.audio.failed.connect(self._audio_failed)
        self.audio.position_changed.connect(self._position)
        self.audio.duration_changed.connect(self._duration)
        self.chunks: list[TextChunk] = []
        self.index = 0
        self.position_ms = 0
        self.duration_ms = 0
        self.active_voice = self.preferred_voice = "af_heart"
        self.active_rate = self.preferred_rate = 1.0
        self.state = "STOPPED"
        self.intent = "stop"
        self.ready = False
        self.voices: list[str] = []
        self.completed = False
        self.navigation_exhausted = False
        self.generation = 0
        self.jobs: dict[int, tuple] = {}
        self.pending_keys: set[tuple] = set()
        self.results: dict[tuple, AudioResult] = {}
        self.current_audio: AudioResult | None = None
        self.init_job: int | None = None
        self.clear_job: int | None = None

    def _invalidate(self) -> None:
        self.generation += 1
        self.worker.cancel_pending("create")
        self.jobs.clear()
        self.pending_keys.clear()

    def initialize_models(self, model: Path, voices: Path) -> None:
        self.stop()
        self.ready = False
        self.results.clear()
        self.worker.cancel_pending()
        self.status.emit("Loading voices on CPU…")
        self.init_job = self.worker.submit("initialize", str(model), str(voices), priority=True)
        self.changed.emit()

    def load(self, chunks: list[TextChunk], progress: ReadingProgress) -> None:
        self.stop()
        self.chunks = chunks
        self.navigation_exhausted = bool(chunks) and all(chunk.page_index < progress.view_page for chunk in chunks)
        self.results.clear()
        self.index = min(max(0, progress.chunk_index), max(0, len(chunks) - 1))
        valid = bool(chunks) and (not progress.chunk_hash or chunks[self.index].text_hash == progress.chunk_hash)
        if not valid and chunks:
            self.index = next((c.index for c in chunks if c.page_index >= progress.view_page), 0)
        self.position_ms = max(0, progress.position_ms) if valid else 0
        self.active_voice, self.active_rate = progress.active_voice, progress.active_rate
        self.preferred_voice, self.preferred_rate = progress.preferred_voice, progress.preferred_rate
        self.completed = bool(progress.completed and valid)
        self._validate_voice()
        self.changed.emit()

    def _validate_voice(self) -> None:
        if not self.voices:
            return
        fallback = "af_heart" if "af_heart" in self.voices else self.voices[0]
        if self.preferred_voice not in self.voices:
            self.preferred_voice = fallback
        if self.active_voice not in self.voices:
            self.active_voice = self.preferred_voice
            self.position_ms = 0

    def snapshot(self, view_page: int) -> ReadingProgress:
        return ReadingProgress(
            view_page, self.index, self.position_ms, self.active_voice, self.active_rate,
            self.preferred_voice, self.preferred_rate,
            self.chunks[self.index].text_hash if self.chunks else "", self.completed,
        )

    def toggle(self) -> None:
        if self.intent == "play":
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if not self.chunks:
            self.status.emit("This page/document has no readable sections yet.")
            return
        if self.navigation_exhausted:
            self.status.emit("There is no readable text on or after this page. Choose an earlier page or section.")
            return
        if not self.ready:
            if self.init_job is not None or self.clear_job is not None:
                self.status.emit("Please wait while the offline voice engine is prepared…")
            else:
                self.setup_requested.emit()
            return
        if self.completed:
            self.select(0, autoplay=False)
        self.intent = "play"
        if self.current_audio and self.duration_ms > 0 and self.position_ms >= self.duration_ms:
            # Seeking to the end while paused must advance on resume rather
            # than letting QMediaPlayer restart that same file from zero.
            self._ended()
            return
        if self.current_audio:
            self.state = "PLAYING"
            self.audio.play()
            self.status.emit("Reading aloud")
        else:
            self.state = "GENERATING"
            self.status.emit("Preparing narration on CPU…")
            self._prepare()
        self.changed.emit()

    def pause(self) -> None:
        self.intent = "pause"
        self.audio.pause()
        self.state = "PAUSED"
        self.status.emit("Paused")
        self.changed.emit()
        self.checkpoint.emit()

    def stop(self) -> None:
        self.intent = "stop"
        self._invalidate()
        self.audio.stop(unload=True)
        self.current_audio = None
        self.position_ms = self.duration_ms = 0
        self.state = "STOPPED"
        self.changed.emit()
        self.checkpoint.emit()

    def select(self, index: int, autoplay: bool | None = None) -> None:
        if not self.chunks:
            return
        should_play = self.intent == "play" if autoplay is None else autoplay
        self.stop()
        self.index = min(max(0, index), len(self.chunks) - 1)
        self.active_voice, self.active_rate = self.preferred_voice, self.preferred_rate
        self.completed = False
        self.navigation_exhausted = False
        self._trim_results()
        self.page_changed.emit(self.chunks[self.index].page_index)
        self.changed.emit()
        self.checkpoint.emit()
        if should_play:
            self.play()

    def navigate_page(self, page: int) -> None:
        self.stop()
        self.completed = False
        selected = next((c.index for c in self.chunks if c.page_index >= page), None)
        self.navigation_exhausted = selected is None
        if selected is not None:
            self.index = selected
            self.active_voice, self.active_rate = self.preferred_voice, self.preferred_rate
        self.changed.emit()

    def previous(self) -> None:
        self.select(self.index - 1)

    def next(self) -> None:
        if self.index + 1 < len(self.chunks):
            self.select(self.index + 1)
        elif self.chunks:
            self.stop()

    def set_preferences(self, voice: str, rate: float) -> None:
        if not 0.5 <= rate <= 2.0 or (self.voices and voice not in self.voices):
            return
        if (voice, rate) == (self.preferred_voice, self.preferred_rate):
            return
        self.preferred_voice, self.preferred_rate = voice, rate
        self._invalidate()
        if self.current_audio is None:
            self.active_voice, self.active_rate = voice, rate
            self.position_ms = 0
            if self.intent in ("play", "pause") and self.ready:
                self._prepare()
        elif self.ready:
            self._prefetch()
        self.status.emit("Voice and speed will apply to the next section." if self.current_audio else "Narration preferences updated")
        self.changed.emit()
        self.checkpoint.emit()

    def seek(self, position_ms: int) -> None:
        if self.current_audio and self.audio.seekable:
            self.position_ms = max(0, min(position_ms, self.duration_ms))
            self.audio.seek(self.position_ms)
            self.changed.emit()
            self.checkpoint.emit()

    def _key(self, index: int, request: SynthesisRequest) -> tuple:
        return index, request.voice, request.rate

    def _request(self, index: int, current: bool = False) -> SynthesisRequest:
        return SynthesisRequest(self.chunks[index].text, self.active_voice if current else self.preferred_voice, self.active_rate if current else self.preferred_rate)

    def _submit(self, index: int, request: SynthesisRequest, priority: bool = False) -> None:
        key = self._key(index, request)
        if key in self.pending_keys or key in self.results:
            return
        protected = tuple({result.path for result in self.results.values()} | ({self.current_audio.path} if self.current_audio else set()))
        job = self.worker.submit("create", request, protected, priority=priority)
        self.jobs[job] = self.generation, index, request
        self.pending_keys.add(key)

    def _prepare(self) -> None:
        request = self._request(self.index, current=True)
        key = self._key(self.index, request)
        cached = self.results.get(key)
        if cached and Path(cached.path).is_file():
            self._start_audio(cached)
        else:
            self.results.pop(key, None)
            self._submit(self.index, request, priority=True)
        self._prefetch()

    def _prefetch(self) -> None:
        self._trim_results()
        for index in range(self.index + 1, min(len(self.chunks), self.index + 3)):
            self._submit(index, self._request(index))

    def _trim_results(self) -> None:
        self.results = {key: value for key, value in self.results.items() if
                        (key[0] == self.index and key[1:] == (self.active_voice, self.active_rate)) or
                        (self.index < key[0] <= self.index + 2 and key[1:] == (self.preferred_voice, self.preferred_rate))}

    def _result(self, job: int, value) -> None:
        if job == self.init_job:
            self.init_job = None
            self.voices = value
            self.ready = True
            self._validate_voice()
            self.voices_changed.emit(value)
            self.status.emit(f"Ready · {len(value)} English voices · offline CPU")
            self.changed.emit()
            return
        if job == self.clear_job:
            self.clear_job = None
            self.ready = bool(self.voices)
            self.status.emit("Audio cache cleared")
            self.changed.emit()
            return
        metadata = self.jobs.pop(job, None)
        if not metadata or metadata[0] != self.generation:
            return
        _, index, request = metadata
        key = self._key(index, request)
        self.pending_keys.discard(key)
        self.results[key] = value
        if index == self.index and request == self._request(index, current=True) and self.intent != "stop":
            self._start_audio(value)

    def _failed(self, job: int, message: str) -> None:
        if job == self.init_job:
            self.init_job = None
            self.ready = False
            self.voices.clear()
            self.voices_changed.emit([])
            self.error.emit(f"Could not load Kokoro voices. Check your model files in Settings.\n\n{message}")
            self.changed.emit()
            return
        if job == self.clear_job:
            self.clear_job = None
            self.ready = bool(self.voices)
            self.error.emit(message)
            self.changed.emit()
            return
        metadata = self.jobs.pop(job, None)
        if not metadata or metadata[0] != self.generation:
            return
        _, index, request = metadata
        self.pending_keys.discard(self._key(index, request))
        if index == self.index:
            self._audio_failed(f"Narration could not be generated. Try another voice or section.\n\n{message}")
        else:
            self.status.emit("The next section could not be prepared; playback will retry when it is reached.")

    def _start_audio(self, result: AudioResult) -> None:
        self.current_audio = result
        self.duration_ms = result.duration_ms
        self.audio.load(result.path, self.position_ms)
        self.changed.emit()

    def _audio_ready(self) -> None:
        if self.current_audio is None or self.intent == "stop":
            return
        if self.intent == "play":
            self.state = "PLAYING"
            self.audio.play()
            self.status.emit("Reading aloud")
            self.page_changed.emit(self.chunks[self.index].page_index)
        else:
            self.state = "PAUSED"
            self.audio.pause()
        self.changed.emit()

    def _ended(self) -> None:
        if self.intent != "play" or self.current_audio is None:
            return
        if self.index + 1 >= len(self.chunks):
            self.intent = "stop"
            self.state = "STOPPED"
            self.completed = True
            self.position_ms = self.duration_ms
            self.status.emit("Finished · press Play to read again")
            self.changed.emit()
            self.checkpoint.emit()
            return
        # Do not invalidate prefetched results at ordinary section boundaries.
        self.intent = "stop"
        self.audio.stop(unload=True)
        self.current_audio = None
        self.index += 1
        self.position_ms = self.duration_ms = 0
        self.active_voice, self.active_rate = self.preferred_voice, self.preferred_rate
        self.page_changed.emit(self.chunks[self.index].page_index)
        self.checkpoint.emit()
        self.play()

    def _audio_failed(self, message: str) -> None:
        self.intent = "stop"
        self._invalidate()
        self.audio.stop(unload=True)
        self.current_audio = None
        self.state = "ERROR"
        self.error.emit(message)
        self.changed.emit()

    def _position(self, value: int) -> None:
        if self.current_audio is not None:
            self.position_ms = value
            self.changed.emit()

    def _duration(self, value: int) -> None:
        if self.current_audio is not None and value:
            self.duration_ms = value
            self.changed.emit()

    def clear_cache(self) -> None:
        self.stop()
        self.results.clear()
        self.ready = False
        self.clear_job = self.worker.submit("clear_cache")
        self.changed.emit()

    def close(self) -> None:
        self.intent = "stop"
        self.audio.stop(unload=True)
        self.worker.shutdown()
