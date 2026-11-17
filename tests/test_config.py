import json

import pytest

from narruvo.config import AppPaths, Settings


def test_configuration_defaults(tmp_path):
    settings = Settings.load(tmp_path / "missing.json")
    assert settings.voice == "af_heart"
    assert settings.rate == 1.0
    assert settings.volume == 0.8
    assert not settings.model_path
    assert settings.model_files(AppPaths(tmp_path))[0] == tmp_path / "models" / "kokoro-v1.0.onnx"


def test_local_data_override(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRUVO_DATA_DIR", str(tmp_path))
    paths = AppPaths.discover()
    paths.ensure()
    assert paths.root == tmp_path.resolve()
    assert paths.models.is_dir() and paths.cache.is_dir() and paths.logs.is_dir()


@pytest.mark.parametrize("new_exists, legacy_exists, expected", [
    (False, False, "Narruvo"),
    (False, True, "VoiceLeaf"),
    (True, False, "Narruvo"),
    (True, True, "Narruvo"),
])
def test_default_data_root_preserves_pre_rename_storage(monkeypatch, tmp_path, new_exists, legacy_exists, expected):
    monkeypatch.delenv("NARRUVO_DATA_DIR", raising=False)
    monkeypatch.delenv("VOICELEAF_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for exists, name in ((new_exists, "Narruvo"), (legacy_exists, "VoiceLeaf")):
        if exists:
            (tmp_path / name).mkdir()
    assert AppPaths.discover().root == tmp_path / expected
    assert (tmp_path / "VoiceLeaf").exists() == legacy_exists
    assert (tmp_path / "Narruvo").exists() == new_exists


def test_legacy_data_override_and_new_override_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv("NARRUVO_DATA_DIR", raising=False)
    monkeypatch.setenv("VOICELEAF_DATA_DIR", str(tmp_path / "existing-data"))
    assert AppPaths.discover().root == (tmp_path / "existing-data").resolve()
    monkeypatch.setenv("NARRUVO_DATA_DIR", str(tmp_path / "chosen-data"))
    assert AppPaths.discover().root == (tmp_path / "chosen-data").resolve()


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    value = Settings(voice="am_michael", rate=1.25, volume=0.4, model_path="C:/models/model.onnx")
    value.save(path)
    assert Settings.load(path) == value
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("data", ["invalid", "[]", '{"volume": "bad", "rate": null}', '{"volume": NaN, "rate": Infinity}'])
def test_invalid_settings_use_safe_defaults(tmp_path, data):
    path = tmp_path / "settings.json"
    path.write_text(data, encoding="utf-8")
    value = Settings.load(path)
    assert value.volume == 0.8 and value.rate == 1.0


def test_settings_clamp_numbers(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume": 12, "rate": -2, "voice": 7}), encoding="utf-8")
    value = Settings.load(path)
    assert value.volume == 1 and value.rate == 0.5 and value.voice == "af_heart"

