# Local verification — 17 November 2026

> Historical snapshot from initial development and packaging. Test counts,
> repository visibility, and release status below describe that verification
> session. Current developer instructions live in the
> [developer handbook](https://dewmith.github.io/Narruvo/).

> These checks predate the rename to **Narruvo**. The VoiceLeaf names, paths,
> and commands below record what was used at the time; current commands use
> the `narruvo` package and `NARRUVO_` environment variables.

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
| `.venv\Scripts\python.exe -m pytest -q` | **66 passed**, 4 integration tests deselected |
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

OCR, password entry, and general-purpose complex-PDF layout reconstruction remain outside the MVP. There are no outstanding installation or model-download blockers. Windows executable packaging was added and verified in the update below.

## Synchronized line highlighting update

- Preserved physical PDF line rectangles through whitespace normalization, dehyphenation, column ordering, and chunk boundaries.
- Used Kokoro's phoneme durations plus batched offline word pronunciation alignment to follow the spoken line. Heart and Michael each produced 17 source-word cues for the real sample, with model timings rather than estimated timing.
- Added a green overlay to the PDF and corresponding Text view selection, automatic scrolling, and a Highlight toggle. Pause holds the current line; seeking updates it immediately; stop/document changes clear it.
- Verified correct geometry at different zoom levels, high DPI, and all four page rotations; repeated text, Unicode, and hyphenated words retain their own coordinates.
- Cached word timing metadata beside each WAV and tested corrupt metadata recovery and paired cache removal. Existing model files and reading progress require no migration; older audio cache entries may be regenerated once.
- Ran the full standard suite: **66 passed**. Ran all real-model integration tests with native Windows widgets: **4 passed**, including playback, voice/rate changes, highlighting, seeking, page transitions, and restart/resume. The native test harness printed the same COM diagnostic documented above, then exited 0.
- Rechecked the updated native script entry point with `run.ps1 -SmokeTest`, Python compilation, dependency consistency, and whitespace checks; all passed.
- Visually inspected `.artifacts/screenshots/line-highlighting.png`, showing the spoken line highlighted on page 2 while paused.

## Windows installer and release automation update

- Added shared Windows CI/build verification, CI on pull requests and `main`, and release uploads on published releases or manual rebuilds of existing release tags. The installer and `.sha256` are the only files uploaded to a release; publishing has a separate job with `contents: write`.
- Pinned PyInstaller 6.22.3, hooks 2026.10, and official Actions commit SHAs. Application runtime versions remain unchanged. Local compilation used Inno Setup 6.7.4; `windows-2022` includes Inno Setup 6.
- Ran the complete ordinary test suite: **76 passed, 4 integration tests deselected**. New cases cover version/tag mismatches, prerelease Windows metadata, real model-free worker checks, native worker failures, and watchdog cleanup. `pip check`, PowerShell parsing, actionlint 1.7.12, and whitespace checks passed.
- Successfully ran `scripts/build.ps1 -ReleaseTag v0.1.0` with an explicit Inno compiler. The unpacked executable and silently installed executable both passed `--verify-package` and `--smoke-test`. Installer verification removed development directories from PATH and unset Python environment overrides.
- Explicitly opted into existing models through `VOICELEAF_TEST_MODELS` for the final local build. Both unpacked and installed builds generated real CPU narration (approximately 2.73 seconds of audio). No models were downloaded or included in the installer. Normal CI checks do not set a model directory.
- The isolated per-user installation was uninstalled successfully. All files in its application-data directory retained their SHA-256 hashes, including settings, the library database, logs, and a preservation marker. Test installation mode suppresses normal uninstall registration and shortcuts.
- Found and resolved an initial native startup error caused by an unrelated tool's incompatible ICU DLL being discovered through the host PATH. The build now isolates native dependency discovery to the Python runtime and Windows directories. The final dependency manifest contains no copies from the unrelated tool runtime.
- The final installer and checksum are under ignored `dist/release/`; package verification logs and development tools are under ignored `.artifacts/`. Installer checks ran in a regular Windows user context because the app sandbox blocks Windows known-folder resolution. No Git commits, pushes, branches, releases, or repository-setting changes were made.

Read-only GitHub inspection confirmed `main` as the default branch, Actions enabled with all actions allowed, and read-only default workflow-token permissions. The publishing job explicitly requests the additional permission it needs. The repository is currently private and has no releases; release downloads require repository access. Immutable releases must remain disabled for the selected publish-then-build flow.

A GitHub prerelease run after pushing these changes is still needed to validate hosted runner execution and actual release uploads. Audible output and Windows 10 hardware still require the manual checks described above; automated packaged synthesis does not confirm speakers/headphones.
