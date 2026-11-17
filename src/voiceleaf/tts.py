"""Offline Kokoro CPU inference and bounded, atomic WAV caching."""

import hashlib
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from voiceleaf.domain import AudioResult, SynthesisRequest
from voiceleaf.models import file_digest
from voiceleaf.text import PROCESSING_VERSION

log = logging.getLogger(__name__)
CACHE_LIMIT = 2 * 1024 ** 3


class AudioCache:
    def __init__(self, directory: Path, limit: int = CACHE_LIMIT):
        self.directory = directory
        self.limit = limit
        directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.wav"

    def lookup(self, key: str) -> AudioResult | None:
        import soundfile as sf

        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            info = sf.info(path)
            if info.frames <= 0 or info.samplerate <= 0 or info.channels != 1:
                raise ValueError("Invalid cached audio")
            path.touch()
            return AudioResult(str(path), round(info.duration * 1000), True)
        except (OSError, ValueError, RuntimeError):
            log.warning("Discarding unreadable audio cache entry %s", path.name)
            path.unlink(missing_ok=True)
            return None

    def prune(self, protected: tuple[str, ...] = (), clear: bool = False) -> None:
        protected_paths = {Path(p).resolve() for p in protected}
        files = sorted(self.directory.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        size = sum(p.stat().st_size for p in files)
        for path in files:
            if not clear and size <= self.limit:
                break
            if path.resolve() in protected_paths:
                continue
            try:
                amount = path.stat().st_size
                path.unlink()
                size -= amount
            except OSError:
                log.warning("Could not remove cached audio %s", path.name, exc_info=True)


class KokoroEngine:
    def __init__(self, cache_directory: Path):
        self.cache = AudioCache(cache_directory)
        self.engine = None
        self.model_fingerprint = ""
        self.voices: list[str] = []

    def initialize(self, model_path: str, voices_path: str) -> list[str]:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        model, voices = Path(model_path), Path(voices_path)
        if not model.is_file() or not voices.is_file():
            raise ValueError("Kokoro files are missing. Open Settings → Set up voices to download or select them.")
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, max(1, (os.cpu_count() or 2) - 1))
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.engine = Kokoro.from_session(session, str(voices))
        self.voices = [v for v in self.engine.get_voices() if v.startswith(("af_", "am_", "bf_", "bm_"))]
        if not self.voices:
            self.engine = None
            raise ValueError("These voice files contain no supported English voices. Select the v1.0 voice file.")
        self.model_fingerprint = file_digest(model) + ":" + file_digest(voices)
        log.info("Kokoro ready on CPU with %d English voices", len(self.voices))
        return self.voices

    def cache_key(self, request: SynthesisRequest) -> str:
        value = [PROCESSING_VERSION, "kokoro-onnx-0.6.1", self.model_fingerprint, request.text, request.voice, request.language, request.rate]
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()

    def create(self, request: SynthesisRequest, protected: tuple[str, ...] = ()) -> AudioResult:
        import numpy as np
        import soundfile as sf

        if self.engine is None:
            raise ValueError("The voice engine is not ready. Set up models in Settings.")
        if request.voice not in self.voices:
            raise ValueError(f"Voice {request.voice} is not installed.")
        if not 0.5 <= request.rate <= 2.0 or not request.text.strip():
            raise ValueError("Choose a rate between 0.5× and 2.0× and a section containing text.")
        key = self.cache_key(request)
        cached = self.cache.lookup(key)
        if cached:
            return cached
        samples, sample_rate = self.engine.create(request.text, voice=request.voice, speed=request.rate, lang=request.language)
        samples = np.asarray(samples).reshape(-1)
        if not len(samples) or not np.isfinite(samples).all() or float(np.max(np.abs(samples))) < 1e-6:
            raise ValueError("The voice engine returned empty or silent audio. Try another voice or section.")
        destination = self.cache.path_for(key)
        temporary = self.cache.directory / f".{key}.{uuid4().hex}.part"
        try:
            sf.write(temporary, samples, sample_rate, format="WAV", subtype="PCM_16")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.cache.prune((*protected, str(destination)))
        return AudioResult(str(destination), round(len(samples) / sample_rate * 1000), False)

    def clear_cache(self) -> None:
        self.cache.prune(clear=True)

