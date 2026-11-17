import numpy as np

from voiceleaf.domain import SynthesisRequest
from voiceleaf.tts import AudioCache, KokoroEngine


class FakeKokoro:
    def __init__(self):
        self.calls = 0

    def create(self, text, voice, speed, lang):
        self.calls += 1
        return np.sin(np.linspace(0, 300, 2400)).astype(np.float32) * 0.2, 24000


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
