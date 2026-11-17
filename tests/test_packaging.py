import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QTimer, Signal

from scripts.package_metadata import read_metadata, write_metadata
from narruvo.config import AppPaths
from narruvo.package_verification import verify_package


def project(tmp_path: Path, version: str = "1.2.3", app_version: str | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    package = tmp_path / "src" / "narruvo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'__version__ = "{app_version or version}"\n', encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("version", ["1.2.3", "1.2.3rc1"])
def test_release_metadata_matches_tag_and_windows_version(tmp_path, version):
    root = project(tmp_path, version)
    output = tmp_path / "build"
    metadata = write_metadata(root, output, f"v{version}")
    assert metadata["installer_name"] == f"Narruvo-{version}-windows-x64-setup.exe"
    assert metadata["windows_version"] == "1.2.3.0"
    assert json.loads((output / "metadata.json").read_text()) == metadata
    assert "filevers=(1, 2, 3, 0)" in (output / "version-info.txt").read_text()


def test_release_tag_mismatch_cannot_generate_assets(tmp_path):
    root = project(tmp_path)
    with pytest.raises(ValueError, match="Release tag"):
        write_metadata(root, tmp_path / "build", "v9.9.9")
    assert not (tmp_path / "build").exists()


def test_app_and_package_versions_must_agree(tmp_path):
    with pytest.raises(ValueError, match="Version mismatch"):
        read_metadata(project(tmp_path, app_version="1.2.2"))


@pytest.mark.parametrize("version", ["1.2", "1.2.3/path", "1.2.70000"])
def test_invalid_installer_versions_are_rejected(tmp_path, version):
    with pytest.raises(ValueError):
        read_metadata(project(tmp_path, version))


def test_package_check_uses_real_native_worker_processes(qapp, tmp_path, monkeypatch):
    monkeypatch.delenv("NARRUVO_TEST_MODELS", raising=False)
    paths = AppPaths(tmp_path)
    assert verify_package(paths) == 0
    assert not list(tmp_path.glob("package-check-*"))
    assert not list(tmp_path.rglob("*.onnx"))
    assert not list(tmp_path.rglob("*.wav"))


@pytest.mark.parametrize("failure", ["worker error", "timeout"])
def test_package_failure_and_timeout_stop_both_workers(qapp, tmp_path, monkeypatch, failure):
    workers = []

    class UnsuccessfulWorker(QObject):
        result = Signal(int, object)
        failed = Signal(int, str)

        def __init__(self, kind, _root):
            super().__init__()
            self.kind = kind
            self.closed = False
            workers.append(self)

        def submit(self, _operation, *_arguments):
            if failure == "worker error" and self.kind == "pdf":
                QTimer.singleShot(0, lambda: self.failed.emit(1, "Native DLL failed to load"))

        def shutdown(self):
            self.closed = True

    monkeypatch.setattr("narruvo.package_verification.ProcessWorker", UnsuccessfulWorker)
    assert verify_package(AppPaths(tmp_path), timeout_ms=25) == 1
    assert len(workers) == 2 and all(worker.closed for worker in workers)
