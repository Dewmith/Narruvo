import hashlib
import io
from threading import Event

import pytest

from voiceleaf.models import DownloadCancelled, ModelAsset, download_models


def asset(data, name="model.onnx"):
    return ModelAsset(name, len(data), hashlib.sha256(data).hexdigest(), "https://example.invalid/" + name)


def test_verified_download_and_reuse(tmp_path):
    data = b"small model test fixture"
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(data)
    progress = []
    result = download_models(tmp_path, lambda *args: progress.append(args), Event(), (asset(data),), opener)
    assert result[0].read_bytes() == data
    assert progress[-1][0] == len(data)
    download_models(tmp_path, lambda *_: None, Event(), (asset(data),), opener)
    assert len(calls) == 1
    assert not list(tmp_path.glob("*.part"))


def test_checksum_failure_preserves_existing_file(tmp_path):
    data = b"expected"
    original = tmp_path / "model.onnx"
    original.write_bytes(b"previous")
    with pytest.raises(ValueError, match="checksum"):
        download_models(tmp_path, lambda *_: None, Event(), (asset(data),), lambda *_args, **_kw: io.BytesIO(b"badxxxxx"))
    assert original.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.part"))


def test_cancellation_cleans_temporary_file(tmp_path):
    data = b"x" * 600000
    cancelled = Event()
    with pytest.raises(DownloadCancelled):
        download_models(tmp_path, lambda *_: cancelled.set(), cancelled, (asset(data),), lambda *_args, **_kw: io.BytesIO(data))
    assert not (tmp_path / "model.onnx").exists()
    assert not list(tmp_path.glob("*.part"))


def test_network_failure_is_reported_and_retryable(tmp_path):
    def offline(*_args, **_kwargs):
        raise OSError("network unavailable")
    with pytest.raises(OSError, match="network unavailable"):
        download_models(tmp_path, lambda *_: None, Event(), (asset(b"ok"),), offline)
    assert not list(tmp_path.glob("*.part"))

