"""Explicit, cancellable downloads from the Kokoro ONNX maintainer's release."""

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True)
class ModelAsset:
    name: str
    size: int
    sha256: str
    url: str


RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1"
_BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
MODEL_ASSETS = (
    ModelAsset("kokoro-v1.0.onnx", 325505369, "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a", _BASE_URL + "kokoro-v1.0.onnx"),
    ModelAsset("voices-v1.0.bin", 28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", _BASE_URL + "voices-v1.0.bin"),
)


class DownloadCancelled(Exception):
    pass


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_models(
    directory: Path,
    progress: Callable[[int, int, str], None],
    cancel: Event,
    assets: tuple[ModelAsset, ...] = MODEL_ASSETS,
    opener: Callable = urllib.request.urlopen,
) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    total, completed = sum(a.size for a in assets), 0
    results = []
    for asset in assets:
        if cancel.is_set():
            raise DownloadCancelled()
        destination = directory / asset.name
        if destination.is_file() and destination.stat().st_size == asset.size and file_digest(destination) == asset.sha256:
            completed += asset.size
            progress(completed, total, asset.name)
            results.append(destination)
            continue
        temporary = directory / f".{asset.name}.{uuid4().hex}.part"
        downloaded = 0
        digest = hashlib.sha256()
        try:
            request = urllib.request.Request(asset.url, headers={"User-Agent": "VoiceLeaf/0.1"})
            with opener(request, timeout=15) as response, temporary.open("wb") as target:
                while True:
                    if cancel.is_set():
                        raise DownloadCancelled()
                    block = response.read(256 * 1024)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > asset.size:
                        raise ValueError(f"{asset.name} has an unexpected size. Check the official release.")
                    target.write(block)
                    digest.update(block)
                    progress(completed + downloaded, total, asset.name)
                target.flush()
                os.fsync(target.fileno())
            if downloaded != asset.size or digest.hexdigest() != asset.sha256:
                raise ValueError(f"{asset.name} failed its size/checksum check. Retry or select verified model files manually.")
            if cancel.is_set():
                raise DownloadCancelled()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        completed += asset.size
        results.append(destination)
    return tuple(results)

