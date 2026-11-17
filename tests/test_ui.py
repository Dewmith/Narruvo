from pathlib import Path

from PySide6.QtCore import Qt

from narruvo.config import AppPaths, Settings
from narruvo.ui.main_window import NarruvoWindow
from narruvo.ui.model_setup import ModelSetupDialog
from narruvo.ui.theme import apply_theme


def make_window(qtbot, qapp, tmp_path):
    paths = AppPaths(tmp_path / "data")
    paths.ensure()
    apply_theme(qapp)
    window = NarruvoWindow(paths, Settings(), show_setup=False)
    qtbot.addWidget(window)
    window.show()
    return window


def test_reader_renders_and_library_progress_survives_window_restart(qtbot, qapp, tmp_path, sample_pdf):
    window = make_window(qtbot, qapp, tmp_path)
    try:
        window.open_pdf(str(sample_pdf))
        qtbot.waitUntil(lambda: window.text_ready and window.viewer.page_image.pixmap() is not None, timeout=20000)
        assert window.current_info.title == "A small book"
        assert len(window.playback.chunks) >= 3
        window.navigate_page(1)
        window.playback.position_ms = 2500
        expected_index = window.playback.index
        document_id = window.current_info.document_id
        window.save_progress()
        assert window.library.get(document_id).progress.view_page == 1
        window.close()
        restored = make_window(qtbot, qapp, tmp_path)
        try:
            restored.open_pdf(str(sample_pdf))
            qtbot.waitUntil(lambda: restored.text_ready, timeout=20000)
            assert restored.current_page == 1
            assert restored.playback.index == expected_index
            assert restored.playback.position_ms == 2500
            assert restored.playback.intent == "stop"
        finally:
            restored.close()
    finally:
        window.close()


def test_responsive_reader_and_visual_artifacts(qtbot, qapp, tmp_path, sample_pdf):
    window = make_window(qtbot, qapp, tmp_path)
    artifacts = Path(__file__).resolve().parents[1] / ".artifacts" / "screenshots"
    artifacts.mkdir(parents=True, exist_ok=True)
    try:
        window.open_pdf(str(sample_pdf))
        qtbot.waitUntil(lambda: window.text_ready and window.viewer.page_image.pixmap() is not None, timeout=20000)
        qtbot.wait(150)
        assert window.grab().save(str(artifacts / "reader-desktop.png"))
        window.resize(1024, 768)
        qtbot.wait(200)
        assert window.width() == 1024 and window.height() == 768
        assert window.sidebar.width() == 78 and not window.recents.isVisible()
        assert window.bar.geometry().right() <= window.centralWidget().width()
        assert window.grab().save(str(artifacts / "reader-laptop.png"))
        window.viewer.text_toggle.setChecked(True)
        qtbot.wait(150)
        assert window.viewer.text.isVisible() and "Chapter" in window.viewer.text.toPlainText()
        assert window.grab().save(str(artifacts / "reader-text.png"))
        window.show_panel(0)
        assert window.grab().save(str(artifacts / "library.png"))
        window.show_panel(2)
        assert window.grab().save(str(artifacts / "settings.png"))
    finally:
        window.close()


def test_missing_models_open_helpful_setup_without_download(qtbot, qapp, tmp_path):
    paths = AppPaths(tmp_path / "first-run")
    paths.ensure()
    window = NarruvoWindow(paths, Settings(), show_setup=True)
    qtbot.addWidget(window)
    window.show()
    try:
        qtbot.waitUntil(lambda: window.setup_dialog is not None, timeout=3000)
        dialog = window.setup_dialog
        assert "354 MB" in dialog.download.text()
        assert dialog.thread is None
        artifacts = Path(__file__).resolve().parents[1] / ".artifacts" / "screenshots"
        artifacts.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(artifacts / "model-setup.png"))
        dialog.reject()
        qtbot.waitUntil(lambda: window.setup_dialog is None)
        assert Settings.load(paths.settings_file).setup_dismissed
    finally:
        window.close()


def test_manual_model_selection(qtbot, tmp_path):
    model, voices = tmp_path / "model.onnx", tmp_path / "voices.bin"
    model.write_bytes(b"validation happens in the worker")
    voices.write_bytes(b"validation happens in the worker")
    dialog = ModelSetupDialog(AppPaths(tmp_path), model, voices)
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.files_selected) as result:
        qtbot.mouseClick(dialog.use, Qt.MouseButton.LeftButton)
    assert result.args == [str(model.resolve()), str(voices.resolve())]


def test_download_failure_reenables_setup_controls(qtbot, tmp_path, monkeypatch):
    def failed_download(*_args):
        raise OSError("test network failure")
    monkeypatch.setattr("narruvo.ui.model_setup.download_models", failed_download)
    dialog = ModelSetupDialog(AppPaths(tmp_path), tmp_path / "model.onnx", tmp_path / "voices.bin")
    qtbot.addWidget(dialog)
    qtbot.mouseClick(dialog.download, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: dialog.thread.isFinished() and dialog.use.isEnabled(), timeout=3000)
    assert "test network failure" in dialog.message.text()
    assert dialog.download.isEnabled() and dialog.skip.isEnabled()


def test_download_cancellation_waits_for_worker_before_closing(qtbot, tmp_path, monkeypatch):
    from narruvo.models import DownloadCancelled
    def cancellable_download(_directory, _progress, cancel):
        cancel.wait(3)
        raise DownloadCancelled()
    monkeypatch.setattr("narruvo.ui.model_setup.download_models", cancellable_download)
    dialog = ModelSetupDialog(AppPaths(tmp_path), tmp_path / "model.onnx", tmp_path / "voices.bin")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.mouseClick(dialog.download, Qt.MouseButton.LeftButton)
    dialog.reject()
    qtbot.waitUntil(lambda: dialog.thread.isFinished() and dialog.skip.isEnabled(), timeout=4000)
    assert "cancelled" in dialog.message.text().lower()
    dialog.reject()
    assert not dialog.isVisible()


def test_invalid_pdf_error_does_not_close_main_window(qtbot, qapp, tmp_path):
    window = make_window(qtbot, qapp, tmp_path)
    try:
        window.open_pdf(str(tmp_path / "missing.pdf"))
        qtbot.waitUntil(lambda: window.error_dialog is not None, timeout=10000)
        assert window.isVisible() and "found" in window.error_dialog.text()
        window.error_dialog.accept()
    finally:
        window.close()


def test_remove_from_library_does_not_delete_pdf(qtbot, qapp, tmp_path, sample_pdf):
    window = make_window(qtbot, qapp, tmp_path)
    try:
        window.open_pdf(str(sample_pdf))
        qtbot.waitUntil(lambda: window.text_ready, timeout=15000)
        window.remove_document(window.current_info.document_id)
        assert sample_pdf.is_file() and window.library.recent() == []
        assert window.current_info is None and window.playback.chunks == []
    finally:
        window.close()
