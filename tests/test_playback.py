from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from voiceleaf.domain import AudioResult, ReadingProgress, SpeechCue, TextChunk
from voiceleaf.playback import PlaybackController


class FakeWorker(QObject):
    result = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.calls = []
        self.closed = False

    def submit(self, operation, *arguments, priority=False):
        job = len(self.calls) + 1
        self.calls.append((job, operation, arguments, priority))
        return job

    def cancel_pending(self, operation=None):
        return []

    def shutdown(self):
        self.closed = True


class FakeAudio(QObject):
    ready = Signal()
    ended = Signal()
    failed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    seekable = True

    def __init__(self):
        super().__init__()
        self.play_calls = 0
        self.loads = []
        self.playing = False

    def load(self, path, position_ms=0):
        self.loads.append((path, position_ms))
        self.ready.emit()

    def play(self):
        self.play_calls += 1
        self.playing = True

    def pause(self):
        self.playing = False

    def stop(self, unload=False):
        self.playing = False

    def seek(self, position):
        self.position_changed.emit(position)


@pytest.fixture
def player(qapp, tmp_path):
    worker, audio = FakeWorker(), FakeAudio()
    controller = PlaybackController(tmp_path, worker=worker, audio=audio)
    controller.ready = True
    controller.voices = ["af_heart", "am_michael"]
    controller.load([TextChunk(i, i // 2, f"Section {i}.") for i in range(6)], ReadingProgress())
    yield controller, worker, audio
    controller.close()


def complete(worker, job, tmp_path):
    path = tmp_path / f"{job}.wav"
    path.write_bytes(b"mock audio")
    result = AudioResult(str(path), 12000, False)
    worker.result.emit(job, result)
    return result


def create_calls(worker):
    return [call for call in worker.calls if call[1] == "create"]


def test_play_prefetches_only_two_sections_then_continues(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    assert len(create_calls(worker)) == 3
    complete(worker, 1, tmp_path)
    assert controller.state == "PLAYING" and audio.playing
    second = complete(worker, 2, tmp_path)
    audio.ended.emit()
    assert controller.index == 1 and controller.state == "PLAYING"
    assert audio.loads[-1][0] == second.path
    assert len(create_calls(worker)) == 4


def test_pause_while_synthesizing_preserves_intent(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    controller.pause()
    complete(worker, 1, tmp_path)
    assert controller.state == "PAUSED" and audio.play_calls == 0
    controller.play()
    assert controller.state == "PLAYING" and audio.play_calls == 1
    assert len(create_calls(worker)) == 3


def test_resume_after_seeking_to_end_advances_instead_of_replaying(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    complete(worker, 1, tmp_path)
    controller.pause()
    controller.seek(controller.duration_ms)
    controller.play()
    assert controller.index == 1 and controller.intent == "play"
    assert controller.state == "GENERATING" and audio.play_calls == 1


def test_stop_rejects_late_results(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    controller.stop()
    complete(worker, 1, tmp_path)
    assert controller.state == "STOPPED" and not audio.loads and not audio.playing


def test_rapid_skips_reject_old_document_or_section_results(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    controller.next()
    controller.next()
    assert controller.index == 2
    complete(worker, 1, tmp_path)
    assert not audio.loads
    current = next(job for job, _, args, _ in reversed(worker.calls) if args[0].text == "Section 2.")
    complete(worker, current, tmp_path)
    assert controller.index == 2 and audio.play_calls == 1


def test_voice_rate_changes_wait_for_next_section(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    complete(worker, 1, tmp_path)
    controller.set_preferences("am_michael", 1.25)
    assert controller.active_voice == "af_heart" and controller.active_rate == 1.0
    progress = controller.snapshot(0)
    assert progress.preferred_voice == "am_michael" and progress.active_voice == "af_heart"
    assert progress.preferred_rate == 1.25 and progress.active_rate == 1.0
    audio.ended.emit()
    assert controller.active_voice == "am_michael" and controller.active_rate == 1.25


def test_preferences_changed_during_generation_replace_unstarted_recipe(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    controller.set_preferences("am_michael", 1.25)
    complete(worker, 1, tmp_path)
    assert not audio.loads
    current = next(job for job, _, args, _ in reversed(worker.calls) if args[0].text == "Section 0.")
    complete(worker, current, tmp_path)
    assert audio.playing and controller.active_voice == "am_michael"


def test_restore_uses_active_recipe_and_position(player, tmp_path):
    controller, worker, audio = player
    progress = ReadingProgress(1, 2, 3500, "af_heart", 0.9, "am_michael", 1.3, controller.chunks[2].text_hash)
    controller.load(controller.chunks, progress)
    controller.play()
    assert worker.calls[0][2][0].voice == "af_heart" and worker.calls[0][2][0].rate == 0.9
    complete(worker, 1, tmp_path)
    assert audio.loads[-1][1] == 3500


def test_navigation_stops_and_selects_page_mapping(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    controller.navigate_page(2)
    complete(worker, 1, tmp_path)
    assert controller.index == 4 and controller.state == "STOPPED" and not audio.loads


def test_navigation_after_last_readable_page_does_not_read_previous_page(player):
    controller, worker, audio = player
    controller.navigate_page(99)
    controller.play()
    assert controller.state == "STOPPED" and not worker.calls and not audio.playing


def test_reopening_on_blank_trailing_page_does_not_read_previous_page(player):
    controller, worker, audio = player
    controller.load(controller.chunks, ReadingProgress(view_page=99))
    controller.play()
    assert controller.state == "STOPPED" and not worker.calls and not audio.playing


def test_final_section_stops_and_play_restarts_book(player, tmp_path):
    controller, worker, audio = player
    controller.select(5, autoplay=True)
    complete(worker, 1, tmp_path)
    audio.ended.emit()
    assert controller.completed and controller.state == "STOPPED"
    controller.play()
    assert not controller.completed and controller.index == 0


def test_failure_is_recoverable(player):
    controller, worker, audio = player
    messages = []
    controller.error.connect(messages.append)
    controller.play()
    worker.failed.emit(1, "mock synthesis error")
    assert controller.state == "ERROR" and messages and not audio.playing
    controller.play()
    assert controller.state == "GENERATING"


def test_duplicate_play_does_not_repeat_synthesis(player):
    controller, worker, _ = player
    controller.play()
    controller.play()
    assert len(create_calls(worker)) == 3


def test_changed_chunk_resets_incompatible_offset(player):
    controller, _, _ = player
    controller.load(controller.chunks, ReadingProgress(2, 1, 9000, chunk_hash="old chunk"))
    assert controller.index == 4 and controller.position_ms == 0


def test_spoken_cue_follows_seek_and_pause_and_clears_on_stop(player, tmp_path):
    controller, worker, audio = player
    controller.play()
    result = AudioResult(str(tmp_path / "timed.wav"), 2000, False, (
        SpeechCue(100, 700, 0, 7), SpeechCue(900, 1500, 8, 10),
    ))
    worker.result.emit(1, result)
    assert controller.reading_cue == result.cues[0]
    audio.position_changed.emit(1000)
    assert controller.reading_cue == result.cues[1]
    controller.pause()
    assert controller.reading_cue == result.cues[1]
    controller.seek(250)
    assert controller.reading_cue == result.cues[0]
    controller.stop()
    assert controller.reading_cue is None

