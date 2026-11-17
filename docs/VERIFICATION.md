# Local verification — 17 November 2026

VoiceLeaf was implemented and exercised in the local repository without commits, pushes, or branch creation. Generated artifacts, the virtual environment, and model binaries are ignored by Git.

## Environment

- Windows x64 host, build 26300; Python 3.12.7 from the existing uv-managed installation.
- The default global `python` points to Python 3.10; the setup script correctly discovers Python 3.12 and the run script uses `.venv` directly.
- All pinned packages installed successfully; `pip check` reports no broken requirements.
- The official full-precision Kokoro model and voice bank were downloaded with explicit authorization into `C:\Users\dewmi\AppData\Local\VoiceLeaf\models` (353,719,767 bytes total). Both release SHA-256 digests passed.
- Kokoro discovers **28 English voices** and runs with **CPUExecutionProvider** only.

## Commands and results

Commands were run from the repository. Longer commands below omit only the explicit absolute path to the existing Python 3.12 executable and isolated test directory arguments.

| Check | Result |
| --- | --- |
| Python 3.12 `-m venv .venv` | Environment created |
| `.venv\Scripts\python.exe -m pip install -e '.[dev]'` | Successful |
| `.\scripts\setup.ps1` | Successful, including automatic Python 3.12 discovery |
| `.venv\Scripts\python.exe scripts\download_models.py --yes` | Both model files downloaded and verified |
| `.venv\Scripts\python.exe -m pytest -q` | **53 passed**, 4 integration tests deselected |
| Real synthesis and Qt playback integration checks | **3 passed** |
| Full PDF window integration with `QT_QPA_PLATFORM=windows` | **1 passed** |
| `.venv\Scripts\python.exe -m voiceleaf --smoke-test` | Exit 0 on native Windows and offscreen platforms |
| `.\scripts\run.ps1 -SmokeTest` | Exit 0 on native Windows |
| `.venv\Scripts\python.exe -m compileall -q src scripts tests` | Successful |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements |

The real-model tests use existing files through `VOICELEAF_TEST_MODELS`; they do not download anything. Normal tests have no model requirement. See README for exact rerun commands.

## Exercised behavior

- Actual PDF extraction and RGB rendering in the dedicated PDF process, including clear columns that MuPDF initially merged into a shared block.
- Blank/image-only, encrypted, corrupt, and missing PDFs; reliable margin cleanup and deterministic page/chunk mappings.
- Library persistence, changed-content resets, relocation identity, and removal without deleting the original.
- Rapid playback controls, cancellation, pause during generation, ignored stale results, bounded prefetch, cache reuse, and voice/rate changes at section boundaries.
- First-run setup without an automatic download, manual model selection, download failure recovery, and cancellation before dialog closure.
- Real CPU synthesis using Heart at 1.0× and Michael at 1.25×: valid, finite, non-silent 24 kHz PCM WAVs, approximately 6.60 and 6.01 seconds respectively.
- Actual Qt Multimedia decoding: 298,238 decoded audio frames across two sections; one Windows audio output was enumerated. Pause, resume, seek, and automatic continuation passed.
- A native Windows main-window flow imported/rendered a PDF, generated narration, changed voice/rate, paused, sought, automatically crossed to page 2, closed, and reopened with the same saved progress and no autoplay.
- Desktop and 1024×768 layouts were rendered and visually inspected, including library, text view, settings, first-run setup, and a reader with real voices loaded.

## Artifacts and verification limits

Generated files are intentionally untracked:

- `.artifacts/screenshots/real-reader.png`: native Windows reader with Michael selected, 1.25× rate, and paused playback on page 2.
- `.artifacts/screenshots/`: desktop, laptop, text, library, settings, and setup previews.
- `.artifacts/real-audio/`: real Heart and Michael sample WAVs.

Automated audio playback was **muted**. Decoding and playback state were verified, but a person should still confirm audible speaker/headphone output using the README acceptance steps. Windows 10 hardware was not separately tested.

The native pytest run printed a Windows COM diagnostic (`0x8001010d`) while inside its nested Qt event loop; the complete test continued and passed with exit 0. The ordinary native application-entry smoke test exited 0 without that diagnostic.

OCR, password entry, executable packaging, and general-purpose complex-PDF layout reconstruction remain outside the MVP. There are no outstanding installation or model-download blockers.
