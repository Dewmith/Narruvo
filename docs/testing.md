# Testing and debugging

## Ordinary tests

Run from the repository root using the application's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

The default pytest configuration excludes the `integration` marker. Tests generate small PDFs in temporary directories and use synthetic/mocked synthesis. The model-free package check loads installed native dependencies and eSpeak resources, but does not download or require models.

| Tests | Primary coverage |
| --- | --- |
| `test_pdf.py`, `test_text.py` | Extraction, rendering, columns, margins, corrupt/encrypted/scanned PDFs, chunks |
| `test_playback.py` | Playback intent, rapid controls, stale results, recipes, bounded prefetch, continuation |
| `test_highlighting.py` | Timing alignment, geometry, zoom/rotation, Unicode, repeated text |
| `test_config.py`, `test_persistence.py` | Settings validation, content identity, saved progress, library removal |
| `test_models.py`, `test_tts_cache.py` | Downloads/checksums/cancellation, paired audio/timing cache, pruning |
| `test_ui.py` | Library, reader, setup dialog, responsive layout, saved progress |
| `test_packaging.py` | Version/tag validation, model-free native workers, failures, watchdog cleanup |

UI tests default to Qt's offscreen platform. Generated screenshots and local verification audio belong under ignored `.artifacts/`.

## Opt-in integration tests

Select existing model files explicitly, then request the integration marker:

```powershell
$env:NARRUVO_TEST_MODELS = Join-Path $env:LOCALAPPDATA 'Narruvo\models'
.\.venv\Scripts\python.exe -m pytest -m integration -s
Remove-Item Env:NARRUVO_TEST_MODELS
```

The directory must contain `kokoro-v1.0.onnx` and `voices-v1.0.bin`. Missing files skip real-model cases; tests never download them. These cases exercise two CPU voices, finite/non-silent PCM audio, speech cues, Qt decoding, pause/resume/seek, automatic continuation, and a complete PDF window flow.

For native Windows widgets:

```powershell
$env:NARRUVO_TEST_MODELS = Join-Path $env:LOCALAPPDATA 'Narruvo\models'
$env:QT_QPA_PLATFORM = 'windows'
.\.venv\Scripts\python.exe -m pytest -m integration tests\test_integration.py::test_real_pdf_window_full_reading_flow -s
Remove-Item Env:QT_QPA_PLATFORM
Remove-Item Env:NARRUVO_TEST_MODELS
```

Automated playback is muted. Audio decoding and state checks do not confirm sound through speakers or headphones.

## Entry-point and package checks

```powershell
.\.venv\Scripts\python.exe -m narruvo --smoke-test
.\scripts\run.ps1 -SmokeTest
.\.venv\Scripts\python.exe -m narruvo --verify-package
```

`--smoke-test` opens the main window briefly without first-run setup. `--verify-package` uses the actual worker protocol to render a generated PDF, check the CPU provider, phonemize English, and round-trip PCM audio. It returns a nonzero exit code on failure and has a 60-second watchdog.

Use an isolated `NARRUVO_DATA_DIR` for these commands when testing state. Frozen executables support the same flags; [packaging verification](packaging.md#verify-the-installer) also tests installation and uninstall.

## Manual acceptance

For changes affecting the complete reading flow:

1. Import a text PDF; check rendered pages and extracted Text view.
2. Select Heart and confirm audible narration on a real audio output.
3. Pause/resume, change volume, seek, and check the synchronized highlight.
4. Change voice/rate while audio is active; check that the next section uses the preference.
5. Continue across sections/pages, then navigate manually and verify narration stops.
6. Close while paused, reopen, and check restored position without autoplay.
7. Remove a library entry and confirm the PDF remains.
8. Use an empty data directory, postpone setup, and confirm PDF viewing works.
9. Disconnect networking after setup and generate a previously uncached section.
10. For UI changes, inspect desktop and 1024×768 layouts, including setup and settings.

## Debug by process

Logs live under the selected data root's `logs/` directory:

| File | Investigate |
| --- | --- |
| `narruvo.log` | Startup, controller/UI errors, package verification, application exceptions |
| `pdf-worker.log` | File access, extraction, rendering, native PDF exceptions |
| `tts-worker.log` | Model loading, phonemization, inference, cache and timing errors |

The app log rotates; worker logs contain native-service tracebacks. Reproduce with an isolated data directory before clearing caches or modifying persisted state. Avoid opening multiple app copies against one data root while testing model/cache maintenance.

**Python/environment errors:** use `.venv\Scripts\python.exe` and confirm it is 3.12 x64. A global Python executable may use another environment. Recreate an incompatible environment rather than mixing package sets.

**Native dependency errors:** check the pinned wheels and CPU architecture. For source installations, verify the compatible x64 Visual C++ runtime. Check whether `PHONEMIZER_ESPEAK_LIBRARY` overrides the packaged loader. The installer build isolates PATH so unrelated tools' DLLs do not enter the bundle.

**Stale UI or unexpected autoplay:** inspect the controller generation, request metadata, and current intent before changing the native service. Add a regression covering the control sequence that produced the error.

**Timing/cache errors:** inspect the WAV and `.timings.json` together. Incompatible metadata is discarded, so apparent cache misses may be deliberate regeneration after a format/version change.

## Verification history

The [dated local verification report](https://github.com/Dewmith/Narruvo/blob/main/docs/VERIFICATION.md) records historical checks, environments, and limitations. It is retained in the repository and excluded from this website. Use current [CI runs](https://github.com/Dewmith/Narruvo/actions) and the commands above to evaluate the current revision.
