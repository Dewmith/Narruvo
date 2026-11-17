import numpy as np
import json
from pathlib import Path

from narruvo.domain import SynthesisRequest
from narruvo.tts import AudioCache, KokoroEngine


class FakeKokoro:
    def __init__(self):
        self.calls = 0

    def create_timed(self, text, voice, speed, lang):
        self.calls += 1
        return np.sin(np.linspace(0, 300, 2400)).astype(np.float32) * 0.2, 24000, []


def test_audio_cache_reuses_synthesis_and_keys_include_recipe(tmp_path):
    engine = KokoroEngine(tmp_path)
    fake = FakeKokoro()
    engine.engine = fake
    engine.voices = ["af_heart", "am_michael"]
    engine.model_fingerprint = "test-model"
    request = SynthesisRequest("Hello world.", "af_heart", 1.0)
    first = engine.create(request)
    second = engine.create(request)
    assert fake.calls == 1 and not first.cache_hit and second.cache_hit
    assert first.path == second.path and first.duration_ms == 100
    assert first.cues == second.cues and first.cues
    assert first.estimated_timings and second.estimated_timings
    assert engine.cache_key(request) != engine.cache_key(SynthesisRequest(request.text, "am_michael", 1.0))
    assert engine.cache_key(request) != engine.cache_key(SynthesisRequest(request.text, "af_heart", 1.25))
    engine.model_fingerprint = "changed-model"
    assert engine.cache.lookup(engine.cache_key(request)) is None


def test_cache_pruning_protects_active_file(tmp_path):
    import soundfile as sf
    cache = AudioCache(tmp_path, limit=100)
    active, old = cache.path_for("active"), cache.path_for("old")
    sf.write(active, np.ones(100), 24000)
    sf.write(old, np.ones(100), 24000)
    cache.prune((str(active),))
    assert active.exists() and not old.exists()
    cache.prune(clear=True)
    assert not active.exists()


def test_corrupt_cache_entry_is_discarded(tmp_path):
    cache = AudioCache(tmp_path)
    cache.path_for("bad").write_bytes(b"not audio")
    assert cache.lookup("bad") is None
    assert not cache.path_for("bad").exists()


def test_corrupt_timing_metadata_regenerates_audio_and_clear_removes_pairs(tmp_path):
    engine = KokoroEngine(tmp_path)
    engine.engine = FakeKokoro()
    engine.voices = ["af_heart"]
    result = engine.create(SynthesisRequest("Hello world.", "af_heart", 1.0))
    metadata_path = engine.cache.timing_path(Path(result.path))
    metadata = json.loads(metadata_path.read_text())
    metadata["cues"][0]["start_ms"] = 999999
    metadata_path.write_text(json.dumps(metadata))
    repaired = engine.create(SynthesisRequest("Hello world.", "af_heart", 1.0))
    assert engine.engine.calls == 2 and repaired.cues
    engine.clear_cache()
    assert not Path(result.path).exists() and not metadata_path.exists()
