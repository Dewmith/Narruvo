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

GitHub release builds synchronize the version automatically. To reproduce a release build locally, synchronize from the chosen tag **before installing the Python package**, then pass that tag to the build script. For example:

```powershell
.\.venv\Scripts\python.exe scripts\package_metadata.py --release-tag v0.3.0 --sync-version
.\.venv\Scripts\python.exe -m pip install -e '.[dev,build]'
.\scripts\build.ps1 -ReleaseTag v0.3.0 -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

| Output | Purpose |
| --- | --- |
| `dist/Narruvo/Narruvo.exe` | Unpacked windowed executable |
| `dist/release/Narruvo-<version>-windows-x64-setup.exe` | Verified per-user installer |
| `dist/release/Narruvo-<version>-windows-x64-setup.exe.sha256` | SHA-256 and installer filename |
| `build/windows/` | Generated version resource and build metadata |
| `.artifacts/package-verification/` | Isolated installation checks and logs |

Build and verification files are ignored by Git. The script rejects PDF/model/audio/database/log file types in the bundle, and isolates PATH during native dependency discovery. This prevents unrelated tool installations from contributing incompatible ICU or other DLLs.

## Version contract

The release tag is the version source for release builds. Publishing a tag such as `v0.3.0` makes the workflow set `0.3.0` in both `pyproject.toml` and `src/narruvo/__init__.py` in its build checkout, before installing dependencies. The Python package metadata, application version, executable resources, installer metadata, installer filename, and checksum filename therefore use that release version. No manual version bump is needed. The release's display title is not parsed; its tag supplies the version.

Use `v<major>.<minor>.<patch>`, optionally followed by `aN`, `bN`, `rcN`, `.postN`, or `.devN`, for example `v0.3.0rc1`. Components must not have leading zeroes, and the major, minor, and patch numbers must be at most 65535 for Windows resources. Prerelease text is retained in the product version and installer filename.

Synchronization updates only the build checkout and does not commit files or move tags. Ordinary CI and local builds without a release tag use the checked-in development version. Both source declarations must still agree, and the metadata helper validates that agreement and the requested tag before bundling. When synchronizing locally, reinstall the Python package afterward so its installed metadata also uses the selected version.

The installer has a stable application identity and default location under `%LOCALAPPDATA%\Programs\Narruvo`. It installs per user without administrator rights, adds a Start menu shortcut, and offers an optional desktop shortcut. Uninstall removes installed app files while preserving the separate data directory and original PDFs.

Upgrades from VoiceLeaf retain the installer identity and previous installation location. The old executable and default shortcuts are replaced with Narruvo names. Existing application data is reused in place as described in [cache and persistence](architecture.md#cache-and-persistence).

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
$env:NARRUVO_DATA_DIR = Join-Path $PWD '.artifacts\real-package-check'
$env:NARRUVO_TEST_MODELS = Join-Path $env:LOCALAPPDATA 'Narruvo\models'
$check = Start-Process -FilePath (Join-Path $PWD 'dist\Narruvo\Narruvo.exe') -ArgumentList '--verify-package' -WindowStyle Hidden -Wait -PassThru
$check.ExitCode
Get-Content (Join-Path $env:NARRUVO_DATA_DIR 'logs\narruvo.log') -Tail 10
Remove-Item Env:NARRUVO_TEST_MODELS
Remove-Item Env:NARRUVO_DATA_DIR
```

No model download occurs. This opts into loading existing models and generating CPU audio; ordinary CI uses model-free verification. Confirm audible output with the [manual acceptance checks](testing.md#manual-acceptance).

## CI and publication flow

:::{container} release-flow
```{mermaid}
flowchart TB
    Release["Published release or manual tag rebuild"]
    Tag["Validate the published release and tag"]
    Version["Set package versions from the release tag"]
    Build["Install, test, and package the tagged source"]
    Verify["Verify workers, installation, and uninstall"]
    Assets["Attach installer and SHA-256 to the release"]
    Release --> Tag --> Version --> Build --> Verify --> Assets
```
:::

A failed test, build, or verification step blocks asset publication. Ordinary pull requests and pushes to `main` also run Windows build verification; they retain workflow artifacts without attaching files to an application release.

The workflows in `.github/workflows/` have separate responsibilities:

| Workflow | Trigger and behavior |
| --- | --- |
| `ci.yml` | Pull requests, pushes to `main`, and manual runs; calls the shared Windows job |
| `windows-build.yml` | Release version synchronization, reusable tests, package compilation, installation verification, and artifact retention |
| `release.yml` | Published releases and manual tag rebuilds; checks out the tag, uses its version, and uploads verified assets |
| `docs.yml` | Documentation validation and publication from `main` |

Official Actions are pinned to commit SHAs. Windows builds run on `windows-2022`, with Python 3.12 and the project's pinned dependencies. The built-in `GITHUB_TOKEN` is sufficient; only the asset-publishing job requests `contents: write`.

## Publish an application release

1. Confirm the intended code, documentation, tests, and workflows are on `main`, and wait for Windows CI to pass on the intended commit.
2. Choose a new supported release tag, such as `v0.3.0`. Its version will be applied automatically during the release build.
3. Keep immutable releases disabled for this publish-then-build workflow. Published immutable releases cannot accept added or replacement assets.
4. Create a matching tag for that tested commit, then publish the release or prerelease on GitHub.
5. Follow [Publish Windows release assets](https://github.com/Dewmith/Narruvo/actions/workflows/release.yml) and verify the resulting installer and checksum.

Draft creation and tag pushes alone do not attach assets. A release stays published if a build fails, so source archives may appear before the executable is ready. Initial installers are unsigned; signing certificates are not part of the current pipeline.

## Recover a failed run

A release tag must include the automatic version synchronization workflow and helper. Older tagged commits retain their original build behavior; updating `main` or rerunning an old release cannot change the workflow or source files stored at that tag.

For an older failure such as `Release tag 'v0.2.0' must match project version v0.1.0`, keep the existing tag and release, commit and push the synchronization changes, and create a new release from the updated, tested commit. For example, publishing `v0.3.0` automatically builds `Narruvo-0.3.0-windows-x64-setup.exe` and its matching `.sha256` file, regardless of the checked-in development version.

- For temporary build failures, inspect job output and the `windows-diagnostics` artifact, then rerun failed jobs.
- If publishing alone failed, rerun that job to reuse its verified artifact.
- To rebuild explicitly, choose **Actions → Publish Windows release assets → Run workflow** and enter the existing published tag. Its commit must already contain the packaging files.
- After artifacts expire, run the complete release workflow again. Installer artifacts are retained for 14 days and diagnostic artifacts for 7 days.
- A source fix gets a new version/tag. Moving an existing release tag makes the published source and binary relationship ambiguous.

Rebuilds replace only the versioned installer and its checksum. Replacement uploads delete the previous same-named assets first; an interrupted upload needs a retry. Other assets and release notes are preserved. See [GitHub release events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release) and [asset upload behavior](https://cli.github.com/manual/gh_release_upload).
