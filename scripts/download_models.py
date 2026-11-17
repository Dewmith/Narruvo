"""Explicit command-line alternative to the in-app model setup dialog."""

import argparse
from pathlib import Path
from threading import Event

from voiceleaf.config import AppPaths
from voiceleaf.models import MODEL_ASSETS, download_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify VoiceLeaf's official Kokoro model files (~354 MB).")
    parser.add_argument("--yes", action="store_true", help="Explicitly accept the model download")
    parser.add_argument("--data-dir", type=Path, help="Override VoiceLeaf's application data directory")
    args = parser.parse_args()
    paths = AppPaths(args.data_dir.resolve()) if args.data_dir else AppPaths.discover()
    print(f"Official Kokoro download: {sum(a.size for a in MODEL_ASSETS) / 1_000_000:.1f} MB to {paths.models}", flush=True)
    if not args.yes and input("Download these files? [y/N] ").strip().lower() != "y":
        print("Download skipped.")
        return
    last_step = -1

    def progress(done: int, total: int, filename: str) -> None:
        nonlocal last_step
        step = int(done / total * 10)
        if step != last_step:
            last_step = step
            print(f"{done / total:.0%} - {filename}", flush=True)

    try:
        for path in download_models(paths.models, progress, Event()):
            print(f"Verified: {path}", flush=True)
    except KeyboardInterrupt:
        raise SystemExit("Download interrupted; run again to retry.")
    except Exception as exc:
        raise SystemExit(f"Download failed: {exc}") from exc


if __name__ == "__main__":
    main()

