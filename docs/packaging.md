# Windows packaging and releases

The Windows installer is a PyInstaller application bundle wrapped by Inno Setup. Runtime Python, Qt plugins, CPU ONNX Runtime, SoundFile, and eSpeak resources are included. Models remain an explicit first-run setup step.

## Build locally

Use Python 3.12 x64 on Windows and install [Inno Setup 6](https://jrsoftware.org/inno-setup/downloads).

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,build]'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\scripts\build.ps1
```

To validate a release tag and select a compiler explicitly:

```powershell
.\scripts\build.ps1 -ReleaseTag v0.1.0 -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

| Output | Purpose |
| --- | --- |
| `dist/VoiceLeaf/VoiceLeaf.exe` | Unpacked windowed executable |
| `dist/release/VoiceLeaf-<version>-windows-x64-setup.exe` | Verified per-user installer |
| `dist/release/VoiceLeaf-<version>-windows-x64-setup.exe.sha256` | SHA-256 and installer filename |
| `build/windows/` | Generated version resource and build metadata |
| `.artifacts/package-verification/` | Isolated installation checks and logs |

Build and verification files are ignored by Git. The script rejects PDF/model/audio/database/log file types in the bundle, and isolates PATH during native dependency discovery. This prevents unrelated tool installations from contributing incompatible ICU or other DLLs.

## Version contract

`pyproject.toml` and `src/voiceleaf/__init__.py` must declare the same version. A release tag must be exactly `v<version>`, such as `v0.1.0` or `v0.2.0rc1`.

The metadata helper validates agreement before bundling and derives numeric Windows version resources from the release components. Prerelease text is retained in the product version and installer filename. Version components must fit Windows resource limits.

The installer has a stable application identity and default location under `%LOCALAPPDATA%\Programs\VoiceLeaf`. It installs per user without administrator rights, adds a Start menu shortcut, and offers an optional desktop shortcut. Uninstall removes installed app files while preserving the separate data directory and original PDFs.

## Verify the installer

The shared build script verifies both the unpacked executable and an isolated installation:

1. Run `--verify-package` through the real worker protocol.
2. Run `--smoke-test` to open and close the window.
3. Silently install into an isolated directory, repeat both checks, and hash user-data files.
4. Uninstall and verify that the executable is removed and user-data hashes are unchanged.
5. Write the installer checksum only after successful verification.

Verification unsets Python environment overrides, removes development-tool directories from PATH, and bounds child processes. Its `/VERIFYINSTALL=1` mode suppresses normal app registration and shortcuts so it can coexist with a user's installed copy. Installer checks need a normal Windows user context with working known-folder resolution.

For an explicit real-model check of the bundle:

```powershell
$env:VOICELEAF_DATA_DIR = Join-Path $PWD '.artifacts\real-package-check'
$env:VOICELEAF_TEST_MODELS = Join-Path $env:LOCALAPPDATA 'VoiceLeaf\models'
$check = Start-Process -FilePath (Join-Path $PWD 'dist\VoiceLeaf\VoiceLeaf.exe') -ArgumentList '--verify-package' -WindowStyle Hidden -Wait -PassThru
$check.ExitCode
Get-Content (Join-Path $env:VOICELEAF_DATA_DIR 'logs\voiceleaf.log') -Tail 10
Remove-Item Env:VOICELEAF_TEST_MODELS
Remove-Item Env:VOICELEAF_DATA_DIR
```

No model download occurs. This opts into loading existing models and generating CPU audio; ordinary CI uses model-free verification. Confirm audible output with the [manual acceptance checks](testing.md#manual-acceptance).

## CI and publication flow

:::{container} release-flow
```{mermaid}
flowchart TB
    Release["Published release or manual tag rebuild"]
    Tag["Validate the published release and tag"]
    Build["Test and package the exact tagged commit"]
    Verify["Verify workers, installation, and uninstall"]
    Assets["Attach installer and SHA-256 to the release"]
    Release --> Tag --> Build --> Verify --> Assets
```
:::

A failed test, build, or verification step blocks asset publication. Ordinary pull requests and pushes to `main` also run Windows build verification; they retain workflow artifacts without attaching files to an application release.

The workflows in `.github/workflows/` have separate responsibilities:

| Workflow | Trigger and behavior |
| --- | --- |
| `ci.yml` | Pull requests, pushes to `main`, and manual runs; calls the shared Windows job |
| `windows-build.yml` | Reusable tests, package compilation, installation verification, and artifact retention |
| `release.yml` | Published releases and manual tag rebuilds; checks out the tag and uploads verified assets |
| `docs.yml` | Documentation validation and publication from `main` |

Official Actions are pinned to commit SHAs. Windows builds run on `windows-2022`, with Python 3.12 and the project's pinned dependencies. The built-in `GITHUB_TOKEN` is sufficient; only the asset-publishing job requests `contents: write`.

## Publish an application release

1. Confirm the intended code, documentation, tests, and workflows are on `main`.
2. Update both version declarations together and run the relevant checks.
3. Keep immutable releases disabled for this publish-then-build workflow. Published immutable releases cannot accept added or replacement assets.
4. Create a matching tag for the intended commit, then publish the release or prerelease on GitHub.
5. Follow [Publish Windows release assets](https://github.com/Dewmith/Text2Voice/actions/workflows/release.yml) and verify the resulting installer and checksum.

Draft creation and tag pushes alone do not attach assets. A release stays published if a build fails, so source archives may appear before the executable is ready. Initial installers are unsigned; signing certificates are not part of the current pipeline.

## Recover a failed run

- For temporary build failures, inspect job output and the `windows-diagnostics` artifact, then rerun failed jobs.
- If publishing alone failed, rerun that job to reuse its verified artifact.
- To rebuild explicitly, choose **Actions → Publish Windows release assets → Run workflow** and enter the existing published tag. Its commit must already contain the packaging files.
- After artifacts expire, run the complete release workflow again. Installer artifacts are retained for 14 days and diagnostic artifacts for 7 days.
- A source fix gets a new version/tag. Moving an existing release tag makes the published source and binary relationship ambiguous.

Rebuilds replace only the versioned installer and its checksum. Replacement uploads delete the previous same-named assets first; an interrupted upload needs a retry. Other assets and release notes are preserved. See [GitHub release events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release) and [asset upload behavior](https://cli.github.com/manual/gh_release_upload).
