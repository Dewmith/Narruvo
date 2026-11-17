"""Application paths and small, validated, atomic JSON settings."""

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppPaths:
    """Local storage with explicit overrides and reuse of pre-rename data."""

    root: Path

    @classmethod
    def discover(cls) -> "AppPaths":
        override = os.getenv("NARRUVO_DATA_DIR") or os.getenv("VOICELEAF_DATA_DIR")
        if override:
            return cls(Path(override).expanduser().resolve())
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        root = base / "Narruvo"
        legacy = base / "VoiceLeaf"
        # Keep existing libraries, model files, and absolute audio paths in place.
        if not root.exists() and legacy.is_dir():
            root = legacy
        return cls(root)

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def cache(self) -> Path:
        return self.root / "audio"

    @property
    def database(self) -> Path:
        return self.root / "library.sqlite3"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> None:
        for path in (self.root, self.models, self.cache, self.logs):
            path.mkdir(parents=True, exist_ok=True)


def bounded_number(value: object, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
        return min(high, max(low, number)) if math.isfinite(number) else default
    except (ValueError, TypeError):
        return default


@dataclass
class Settings:
    """Validated preferences persisted by atomic JSON file replacement."""

    voice: str = "af_heart"
    rate: float = 1.0
    volume: float = 0.8
    model_path: str = ""
    voices_path: str = ""
    last_document_id: str = ""
    setup_dismissed: bool = False

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Settings must be an object")
            result = cls()
            for key in ("voice", "model_path", "voices_path", "last_document_id"):
                if isinstance(data.get(key), str):
                    setattr(result, key, data[key])
            result.rate = bounded_number(data.get("rate", 1.0), 0.5, 2.0, 1.0)
            result.volume = bounded_number(data.get("volume", 0.8), 0.0, 1.0, 0.8)
            result.setup_dismissed = data.get("setup_dismissed") is True
            return result
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.warning("Could not read settings; using defaults", exc_info=True)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)

    def model_files(self, paths: AppPaths) -> tuple[Path, Path]:
        return (
            Path(self.model_path) if self.model_path else paths.models / "kokoro-v1.0.onnx",
            Path(self.voices_path) if self.voices_path else paths.models / "voices-v1.0.bin",
        )

