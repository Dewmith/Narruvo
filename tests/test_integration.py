"""Opt-in real-model and real-multimedia checks; never download anything."""

import os
import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtMultimedia import QAudioBufferOutput, QMediaDevices, QMediaPlayer
from PySide6.QtCore import Qt

from narruvo.config import AppPaths
from narruvo.config import Settings
from narruvo.domain import ReadingProgress, SynthesisRequest, TextChunk
from narruvo.playback import PlaybackController
from narruvo.tts import KokoroEngine
from narruvo.ui.main_window import NarruvoWindow
from narruvo.ui.theme import apply_theme

pytestmark = pytest.mark.integration


def model_files():
    root = Path(os.environ.get("NARRUVO_TEST_MODELS", str(AppPaths.discover().models)))
    model, voices = root / "kokoro-v1.0.onnx", root / "voices-v1.0.bin"
    if not model.is_file() or not voices.is_file():
        pytest.skip("Download models explicitly, or set NARRUVO_TEST_MODELS to their directory")
    return model, voices


@pytest.fixture(scope="module")
def real_engine():
    model, voices = model_files()
    root = Path(__file__).resolve().parents[1] / ".artifacts" / "real-audio"
    engine = KokoroEngine(root)
    installed = engine.initialize(str(model), str(voices))
    assert len(installed) >= 2
    assert engine.engine.sess.get_providers() == ["CPUExecutionProvider"]
    return engine


@pytest.mark.parametrize("voice,rate", [("af_heart", 1.0), ("am_michael", 1.25)])
def test_real_offline_cpu_synthesis(real_engine, voice, rate):
    request = SynthesisRequest("Welcome to Narruvo. Your books stay on your computer, and your natural reading voice works entirely offline.", voice, rate)
    result = real_engine.create(request)
    samples, sample_rate = sf.read(result.path)
    assert sample_rate == 24000 and result.duration_ms > 1000
    assert np.isfinite(samples).all() and np.max(np.abs(samples)) > 0.01
    assert [request.text[cue.text_start:cue.text_end] for cue in result.cues] == re.findall(r"\S+", request.text)
    assert all(0 <= cue.start_ms <= cue.end_ms <= result.duration_ms for cue in result.cues)
    assert real_engine.create(request).cache_hit
    print(f"CPU voice={voice} rate={rate} duration={result.duration_ms}ms cues={len(result.cues)} estimated={result.estimated_timings} WAV={result.path}")


def test_real_worker_and_qt_playback_pause_seek_and_continuation(qtbot, tmp_path):
    model, voices = model_files()
    controller = PlaybackController(tmp_path)
    failures, pages, positions, decoded = [], [], [], []
    controller.error.connect(failures.append)
    controller.page_changed.connect(pages.append)
    controller.audio.position_changed.connect(positions.append)
    buffer_output = QAudioBufferOutput(controller.audio)
    buffer_output.audioBufferReceived.connect(lambda buffer: decoded.append(buffer.frameCount()))
    controller.audio.player.setAudioBufferOutput(buffer_output)
    controller.audio.set_volume(0.0)
    try:
        controller.initialize_models(model, voices)
        qtbot.waitUntil(lambda: controller.ready or bool(failures), timeout=60000)
        assert not failures
        controller.load([
            TextChunk(0, 0, "This is the first section of your book. You can pause the narration, resume it, and move through the page at your own pace."),
            TextChunk(1, 1, "The reader has automatically continued to the next page. Your reading progress will be saved locally."),
        ], ReadingProgress())
        controller.play()
        qtbot.waitUntil(lambda: controller.state == "PLAYING" or bool(failures), timeout=60000)
        assert not failures
        qtbot.waitUntil(lambda: controller.position_ms > 100, timeout=10000)
        controller.pause()
        qtbot.waitUntil(lambda: controller.audio.player.playbackState() == QMediaPlayer.PlaybackState.PausedState, timeout=5000)
        assert controller.state == "PAUSED"
        assert controller.audio.seekable
        controller.seek(500)
        qtbot.waitUntil(lambda: abs(controller.position_ms - 500) < 150, timeout=5000)
        controller.play()
        qtbot.waitUntil(lambda: controller.completed or bool(failures), timeout=60000)
        assert not failures and 1 in pages
        assert any(position > 500 for position in positions)
        assert sum(decoded) > 1000
        print(f"Qt decoded {sum(decoded)} frames; automatic continuation passed; audio devices={len(QMediaDevices.audioOutputs())}")
    finally:
        controller.close()


def test_real_pdf_window_full_reading_flow(qtbot, qapp, tmp_path, sample_pdf):
    model, voices = model_files()
    paths = AppPaths(tmp_path / "real-ui")
    paths.ensure()
    settings = Settings(model_path=str(model), voices_path=str(voices), volume=0.0)
    apply_theme(qapp)
    window = NarruvoWindow(paths, settings, str(sample_pdf), show_setup=False)
    qtbot.addWidget(window)
    window.show()
    failures = []
    window.playback.error.connect(failures.append)
    try:
        qtbot.waitUntil(lambda: (window.text_ready and window.playback.ready) or bool(failures), timeout=60000)
        assert not failures
        # Start near the first page's end to exercise a genuine page transition.
        last_on_first_page = max(c.index for c in window.playback.chunks if c.page_index == 0)
        window.playback.select(last_on_first_page, autoplay=False)
        qtbot.mouseClick(window.bar.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: window.playback.state == "PLAYING" or bool(failures), timeout=60000)
        assert not failures
        qtbot.waitUntil(lambda: bool(window.viewer.page_image.highlight_rects), timeout=5000)
        assert window.playback.reading_cue is not None
        assert window.viewer.text.extraSelections()
        voice_index = window.bar.voice.findData("am_michael")
        assert voice_index >= 0
        window.bar.voice.setCurrentIndex(voice_index)
        window.bar.voice.activated.emit(voice_index)
        window.bar.rate.setValue(1.25)
        assert window.playback.active_voice == "af_heart"
        qtbot.mouseClick(window.bar.play, Qt.MouseButton.LeftButton)
        assert window.playback.state == "PAUSED"
        qtbot.waitUntil(lambda: window.playback.audio.seekable, timeout=5000)
        window.playback.seek(max(0, window.playback.duration_ms - 700))
        qtbot.mouseClick(window.bar.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: (window.playback.index > last_on_first_page and window.playback.state == "PLAYING") or bool(failures), timeout=60000)
        assert not failures
        assert window.current_page == 1
        assert window.playback.active_voice == "am_michael" and window.playback.active_rate == 1.25
        qtbot.waitUntil(lambda: bool(window.viewer.page_image.highlight_rects), timeout=5000)
        qtbot.mouseClick(window.bar.play, Qt.MouseButton.LeftButton)
        window.playback.seek(1000)
        qtbot.waitUntil(lambda: abs(window.playback.position_ms - 1000) < 150, timeout=5000)
        highlighted = window.viewer.page_image.highlight_rects
        assert highlighted
        qtbot.wait(150)
        assert window.viewer.page_image.highlight_rects == highlighted
        window.viewer.highlight_toggle.setChecked(False)
        assert not window.viewer.page_image.highlight_rects
        window.viewer.highlight_toggle.setChecked(True)
        assert window.viewer.page_image.highlight_rects
        window.save_progress()
        expected = window.playback.snapshot(window.current_page)
        artifacts = Path(__file__).resolve().parents[1] / ".artifacts" / "screenshots"
        artifacts.mkdir(parents=True, exist_ok=True)
        window.resize(1024, 768)
        qtbot.wait(300)
        assert window.grab().save(str(artifacts / "real-reader.png"))
        assert window.grab().save(str(artifacts / "line-highlighting.png"))
        window.close()
        restored = NarruvoWindow(paths, Settings.load(paths.settings_file), show_setup=False)
        qtbot.addWidget(restored)
        restored.show()
        try:
            qtbot.waitUntil(lambda: restored.text_ready, timeout=30000)
            progress = restored.playback.snapshot(restored.current_page)
            assert progress == expected
            assert restored.playback.intent == "stop"
        finally:
            restored.close()
        print("Full PDF window flow passed: render, synchronized line highlighting, voice/rate selection, pause, seek, automatic page transition, restart/resume")
    finally:
        window.close()
