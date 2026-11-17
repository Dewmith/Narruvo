"""Offline Kokoro CPU inference and bounded, atomic WAV caching."""

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from voiceleaf.domain import AudioResult, PackageCheckResult, SpeechCue, SynthesisRequest
from voiceleaf.models import file_digest
from voiceleaf.text import PROCESSING_VERSION
from voiceleaf.timing import align_cues, estimated_cues

log = logging.getLogger(__name__)
CACHE_LIMIT = 2 * 1024 ** 3
AUDIO_VERSION = "voiceleaf-audio-v2-timed"


class AudioCache:
    """Worker-owned WAV/timing cache with validation and protected-path pruning."""

    def __init__(self, directory: Path, limit: int = CACHE_LIMIT):
        self.directory = directory
        self.limit = limit
        directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.wav"

    @staticmethod
    def timing_path(path: Path) -> Path:
        return path.with_suffix(".timings.json")

    def lookup(self, key: str) -> AudioResult | None:
        """Return a valid audio/timing pair or discard an incompatible cache entry."""
        import soundfile as sf

        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            info = sf.info(path)
            if info.frames <= 0 or info.samplerate <= 0 or info.channels != 1:
                raise ValueError("Invalid cached audio")
            duration_ms = round(info.duration * 1000)
            metadata = json.loads(self.timing_path(path).read_text(encoding="utf-8"))
            if metadata["version"] != 1 or abs(metadata["duration_ms"] - duration_ms) > 1:
                raise ValueError("Invalid cached timing metadata")
            cues = tuple(SpeechCue(**value) for value in metadata["cues"])
            previous_end = 0
            previous_text_end = 0
            for cue in cues:
                if (any(type(value) is not int for value in asdict(cue).values()) or
                    not previous_end <= cue.start_ms <= cue.end_ms <= duration_ms or
                    not previous_text_end <= cue.text_start < cue.text_end <= metadata["text_length"]):
                    raise ValueError("Invalid cached speech timing")
                previous_end, previous_text_end = cue.end_ms, cue.text_end
            if not cues or type(metadata["estimated"]) is not bool:
                raise ValueError("Missing cached speech timing")
            path.touch()
            return AudioResult(str(path), duration_ms, True, cues, metadata["estimated"])
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            log.warning("Discarding unreadable audio cache entry %s", path.name)
            path.unlink(missing_ok=True)
            self.timing_path(path).unlink(missing_ok=True)
            return None

    def prune(self, protected: tuple[str, ...] = (), clear: bool = False) -> None:
        """Remove oldest audio pairs toward the size limit, preserving references."""
        protected_paths = {Path(p).resolve() for p in protected}
        files = sorted(self.directory.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        def pair_size(path):
            metadata = self.timing_path(path)
            return path.stat().st_size + (metadata.stat().st_size if metadata.is_file() else 0)
        size = sum(pair_size(p) for p in files)
        for path in files:
            if not clear and size <= self.limit:
                break
            if path.resolve() in protected_paths:
                continue
            try:
                amount = pair_size(path)
                path.unlink()
                self.timing_path(path).unlink(missing_ok=True)
                size -= amount
            except OSError:
                log.warning("Could not remove cached audio %s", path.name, exc_info=True)
        for metadata in self.directory.glob("*.timings.json"):
            if not metadata.with_name(metadata.name.removesuffix(".timings.json") + ".wav").exists():
                try:
                    metadata.unlink()
                except OSError:
                    log.warning("Could not remove orphaned timing data %s", metadata.name)


class KokoroEngine:
    """CPU speech service whose initialization and cache work stay off the GUI."""

    def __init__(self, cache_directory: Path):
        self.cache = AudioCache(cache_directory)
        self.engine = None
        self.model_fingerprint = ""
        self.voices: list[str] = []

    def verify_runtime(self, model_directory: str | None = None) -> PackageCheckResult:
        """Check bundled native libraries without downloading or requiring models."""
        import importlib.metadata

        import numpy as np
        import onnxruntime as ort
        import soundfile as sf
        from kokoro_onnx.tokenizer import Tokenizer

        if "CPUExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("The packaged ONNX Runtime CPU provider is unavailable")
        # Kokoro uses package metadata at runtime, including in frozen builds.
        importlib.metadata.version("kokoro-onnx")
        tokenizer = Tokenizer()
        for language in ("en-us", "en-gb"):
            if not tokenizer.phonemize("VoiceLeaf reads offline.", lang=language):
                raise RuntimeError(f"Packaged eSpeak resources failed for {language}")
        samples = np.sin(np.arange(2400) * (2 * np.pi * 440 / 24000)).astype(np.float32) * 0.1
        buffer = BytesIO()
        sf.write(buffer, samples, 24000, format="WAV", subtype="PCM_16")
        buffer.seek(0)
        decoded, sample_rate = sf.read(buffer)
        if sample_rate != 24000 or len(decoded) != len(samples) or not np.isfinite(decoded).all():
            raise RuntimeError("Packaged SoundFile could not round-trip PCM audio")
        detail = "CPU ONNX Runtime, English phonemization, and PCM audio verified without models"
        # This is deliberately opt-in, using the same variable as integration tests.
        if model_directory:
            root = Path(model_directory)
            voices = self.initialize(str(root / "kokoro-v1.0.onnx"), str(root / "voices-v1.0.bin"))
            voice = "af_heart" if "af_heart" in voices else voices[0]
            result = self.create(SynthesisRequest("VoiceLeaf reads your books entirely offline.", voice, 1.0))
            if result.duration_ms <= 0:
                raise RuntimeError("Packaged model synthesis returned no audio")
            detail += f"; real CPU synthesis verified ({result.duration_ms} ms)"
        return PackageCheckResult("tts", detail)

    def initialize(self, model_path: str, voices_path: str) -> list[str]:
        """Load and fingerprint local models, returning supported English voice IDs.

        Native initialization and hashing both files can block; invoke this
        in the TTS process with explicitly selected/downloaded model files.
        """
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
        value = [AUDIO_VERSION, PROCESSING_VERSION, "kokoro-onnx-0.6.1", self.model_fingerprint, request.text, request.voice, request.language, request.rate]
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).hexdigest()

    def create(self, request: SynthesisRequest, protected: tuple[str, ...] = ()) -> AudioResult:
        """Reuse or generate a recipe's audio/cues and prune unprotected cache.

        Initialization must succeed first. Invalid recipes and unusable
        generated samples raise ``ValueError``.
        """
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
        samples, sample_rate, timings = self.engine.create_timed(request.text, voice=request.voice, speed=request.rate, lang=request.language)
        samples = np.asarray(samples).reshape(-1)
        if not len(samples) or not np.isfinite(samples).all() or float(np.max(np.abs(samples))) < 1e-6:
            raise ValueError("The voice engine returned empty or silent audio. Try another voice or section.")
        duration_ms = round(len(samples) / sample_rate * 1000)
        cues, estimated = self._speech_cues(request, timings, duration_ms)
        destination = self.cache.path_for(key)
        temporary = self.cache.directory / f".{key}.{uuid4().hex}.part"
        timing_temporary = self.cache.directory / f".{key}.{uuid4().hex}.part"
        try:
            sf.write(temporary, samples, sample_rate, format="WAV", subtype="PCM_16")
            timing_temporary.write_text(json.dumps({
                "version": 1, "duration_ms": duration_ms, "text_length": len(request.text),
                "estimated": estimated, "cues": [asdict(cue) for cue in cues],
            }), encoding="utf-8")
            temporary.replace(destination)
            timing_temporary.replace(self.cache.timing_path(destination))
        finally:
            temporary.unlink(missing_ok=True)
            timing_temporary.unlink(missing_ok=True)
        self.cache.prune((*protected, str(destination)))
        return AudioResult(str(destination), duration_ms, False, cues, estimated)

    def _speech_cues(self, request, timings, duration_ms):
        if timings:
            try:
                from phonemizer import phonemize
                words = re.findall(r"\S+", request.text)
                pronunciations = phonemize(words, language=request.language, preserve_punctuation=True, with_stress=True, njobs=1)
                pronunciations = [self.engine.tokenizer.known(value) for value in pronunciations]
                return align_cues(request.text, timings, pronunciations, duration_ms)
            except Exception:
                log.warning("Word alignment unavailable; estimating highlight timing", exc_info=True)
        return estimated_cues(request.text, duration_ms), True

    def clear_cache(self) -> None:
        self.cache.prune(clear=True)

