import json
import runpy
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QTimer, Signal

from scripts.package_metadata import read_metadata, sync_version, write_metadata
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


@pytest.mark.parametrize("version,windows_version", [
    ("0.2.0", "0.2.0.0"),
    ("0.3.0", "0.3.0.0"),
    ("2.4.6rc1", "2.4.6.0"),
    ("2.4.6a0", "2.4.6.0"),
    ("2.4.6b2", "2.4.6.0"),
    ("2.4.6.post1", "2.4.6.0"),
    ("2.4.6.dev0", "2.4.6.0"),
])
def test_release_tag_synchronizes_stale_source_and_build_versions(tmp_path, version, windows_version):
    root = project(tmp_path, version="0.1.0", app_version="0.0.9")
    sync_version(root, f"v{version}")
    metadata = write_metadata(root, tmp_path / "build", f"v{version}")

    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"] == version
    assert runpy.run_path(str(root / "src" / "narruvo" / "__init__.py"))["__version__"] == version
    assert metadata == {
        "version": version,
        "windows_version": windows_version,
        "installer_name": f"Narruvo-{version}-windows-x64-setup.exe",
    }
    assert json.loads((root / "build" / "metadata.json").read_text()) == metadata
    resource = (root / "build" / "version-info.txt").read_text()
    assert f"StringStruct('FileVersion', {version!r})" in resource
    assert f"StringStruct('ProductVersion', {version!r})" in resource


def test_version_sync_preserves_other_content_and_can_be_repeated(tmp_path):
    root = project(tmp_path)
    project_path = root / "pyproject.toml"
    package_path = root / "src" / "narruvo" / "__init__.py"
    project_source = (
        '# Keep this comment.\r\n[project]\r\nversion = \'1.2.3\' # package version\r\n'
        'description = "Version 1.2.3"\r\n[tool.example]\r\nversion = "1.2.3"\r\n'
    )
    package_source = (
        '"""Version 1.2.3."""\r\n\r\n'
        '__version__ = "1.2.3"  # app version\r\nOTHER_VALUE = "1.2.3"\r\n'
    )
    project_path.write_bytes(project_source.encode("utf-8"))
    package_path.write_bytes(package_source.encode("utf-8"))
    expected_project = project_source.replace("version = '1.2.3'", "version = '0.3.0'").encode("utf-8")
    expected_package = package_source.replace('__version__ = "1.2.3"', '__version__ = "0.3.0"').encode("utf-8")

    for _ in range(2):
        sync_version(root, "v0.3.0")
        assert project_path.read_bytes() == expected_project
        assert package_path.read_bytes() == expected_package


@pytest.mark.parametrize("tag", [
    "", "0.3.0", "V0.3.0", "v1.2", "v1.2.3-beta.1", "v1.2.3/path", "v1.2.3\n",
    "v1.2.70000", "v01.2.3", "v1.2.3rc01",
])
def test_invalid_release_tags_do_not_change_source_files(tmp_path, tag):
    root = project(tmp_path)
    paths = [root / "pyproject.toml", root / "src" / "narruvo" / "__init__.py"]
    original = [path.read_bytes() for path in paths]
    with pytest.raises(ValueError):
        sync_version(root, tag)
    assert [path.read_bytes() for path in paths] == original


def test_version_sync_checks_both_files_before_changing_either(tmp_path):
    root = project(tmp_path)
    project_path = root / "pyproject.toml"
    package_path = root / "src" / "narruvo" / "__init__.py"
    package_path.write_text('"""No version assignment."""\n', encoding="utf-8")
    original_project = project_path.read_bytes()
    original_package = package_path.read_bytes()
    with pytest.raises(ValueError, match="__version__"):
        sync_version(root, "v0.3.0")
    assert project_path.read_bytes() == original_project
    assert package_path.read_bytes() == original_package


@pytest.mark.parametrize("synchronize", [False, True])
def test_release_metadata_command_only_synchronizes_when_requested(tmp_path, synchronize):
    root = project(tmp_path, version="0.1.0")
    script = root / "scripts" / "package_metadata.py"
    script.parent.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts" / "package_metadata.py", script)
    output = root / "build" / "windows"
    command = [sys.executable, str(script), "--release-tag", "v0.3.0", "--output-dir", str(output)]
    if synchronize:
        command.append("--sync-version")
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=20)

    if synchronize:
        assert result.returncode == 0, result.stderr
        metadata = json.loads(result.stdout)
        assert metadata["version"] == "0.3.0"
        assert metadata["installer_name"] == "Narruvo-0.3.0-windows-x64-setup.exe"
        assert json.loads((output / "metadata.json").read_text()) == metadata
        assert read_metadata(root, "v0.3.0") == metadata
    else:
        assert result.returncode != 0
        assert "Release tag 'v0.3.0' must match project version v0.1.0" in result.stderr
        assert not output.exists()
        assert read_metadata(root)["version"] == "0.1.0"


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
