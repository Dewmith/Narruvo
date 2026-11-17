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

The release tag is the version source for release builds. Pushing a tag such as `v0.4.0`, or publishing a GitHub release for it, makes the workflow set `0.4.0` in both `pyproject.toml` and `src/narruvo/__init__.py` in its build checkout, before installing dependencies. The Python package metadata, application version, executable resources, installer metadata, installer filename, and checksum filename therefore use that release version. No manual version bump is needed. The release's display title is not parsed; its tag supplies the version.

Use `v<major>.<minor>.<patch>`, optionally followed by `aN`, `bN`, `rcN`, `.postN`, or `.devN`, for example `v0.3.0rc1`. Components must not have leading zeroes, and the major, minor, and patch numbers must be at most 65535 for Windows resources. Prerelease text is retained in the product version and installer filename.

When the workflow creates a new release, plain versions and `.postN` versions are stable releases; `aN`, `bN`, `rcN`, and `.devN` versions are prereleases. Existing releases keep their selected type, title, and notes, even when their type differs from the tag's default.

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
    Push["Push a version tag"]
    Release["Publish a GitHub release"]
    Manual["Request a manual tag rebuild"]
    Tag["Validate tag and inspect existing assets"]
    Version["Set package versions from the release tag"]
    Build["Install, test, and package the tagged source"]
    Verify["Verify workers, installation, and uninstall"]
    Draft["Create a missing release as a draft"]
    Assets["Attach installer and SHA-256"]
    Publish["Publish a completed draft or finish the existing release"]
    Push --> Tag
    Release --> Tag
    Manual --> Tag
    Tag --> Version --> Build --> Verify --> Draft --> Assets --> Publish
```
:::

A failed test, build, or verification step blocks asset publication. For a tag with no release, the workflow creates the draft only after the build passes, uploads both verified files, and publishes the draft. Existing drafts are completed through the same process. A release published manually is already visible while its build runs; failed builds leave that release available without new installer assets.

All release runs share a concurrency group for their resolved tag. An active run is allowed to finish. When a second automatic event for that tag starts, it skips packaging if the published release already has the expected, nonempty installer and checksum in the uploaded state. Rerunning a completed automatic workflow also skips duplicate packaging. Manual dispatch explicitly requests a rebuild instead.

Ordinary pull requests and pushes to `main` also run Windows build verification; they retain workflow artifacts without attaching files to an application release.

The workflows in `.github/workflows/` have separate responsibilities:

| Workflow | Trigger and behavior |
| --- | --- |
| `ci.yml` | Pull requests, pushes to `main`, and manual runs; calls the shared Windows job |
| `windows-build.yml` | Release version synchronization, reusable tests, package compilation, installation verification, and artifact retention |
| `release.yml` | Version tag pushes, published releases, and manual rebuilds; builds tagged source, uploads verified assets, and publishes completed drafts |
| `docs.yml` | Documentation validation and publication from `main` |

Official Actions are pinned to commit SHAs. Windows builds run on `windows-2022`, with Python 3.12 and the project's pinned dependencies. The built-in `GITHUB_TOKEN` is sufficient; only the asset-publishing job requests `contents: write`. Preparation and publication use the dependency-free `scripts/github_release.py` helper. The workflow completes the entire release itself: a release published using `GITHUB_TOKEN` does not trigger a second release workflow. See [GitHub token event behavior](https://docs.github.com/en/actions/concepts/security/github_token#when-github_token-triggers-workflow-runs).

The helper finds drafts through authenticated, paginated release listings because GitHub's lookup by tag only returns published releases. This lets the publishing job retrieve new drafts and resume interrupted uploads without replacing their metadata.

## Publish an application release

First confirm the intended code and workflows are on `main`, and wait for Windows CI to pass on the commit being released. Choose a new supported version tag. Either entry point produces the installer and checksum:

- **Push a tag:** create an annotated tag on that tested commit, then push that specific tag. For example, `git tag -a v0.4.0 -m "Narruvo v0.4.0"`, then `git push origin refs/tags/v0.4.0`. The workflow builds the installer and publishes its GitHub release automatically. Use a tag such as `v0.4.0rc1` for an automatic prerelease.
- **Publish on GitHub:** use **Releases → Draft a new release**, select an existing tag or create one on the tested commit, choose the release type and notes, and publish. The workflow builds and attaches the installer while preserving that metadata. Saving a draft alone does not trigger a build; a version tag push or release publication does.

Keep immutable releases disabled when using release-first publication: an already published immutable release cannot accept installer uploads. Tag-first publication uploads assets before publishing the draft and can work with immutability enabled. A completed immutable release can be skipped safely, but rebuilding or completing an immutable published release fails with an explanation.

Follow [Publish Windows release assets](https://github.com/Dewmith/Narruvo/actions/workflows/release.yml) and confirm the versioned installer and `.sha256` file appear in the release's **Assets**. Initial installers are unsigned; signing certificates are not part of the current pipeline.

## Recover a failed run

A release tag must include the workflows and helpers for the desired release behavior. Older tagged commits retain their original behavior; updating `main` or rerunning an old tagged workflow cannot change its source. Existing tags and release assets, including `v0.3.0`, do not move when this automation is updated. Create future tags from the updated, tested commit.

- For temporary build failures, inspect job output and the `windows-diagnostics` artifact, then rerun failed jobs.
- If publishing alone failed, rerun failed jobs to reuse the verified artifact. An interrupted new release remains a draft until both uploads succeed; a retry reuses that draft and preserves its notes and type.
- To rebuild explicitly, choose **Actions → Publish Windows release assets → Run workflow** on `main` and enter an existing version tag. Unlike automatic events, this rebuilds even if both assets already exist. Its tagged source must contain the packaging files; no published release is required.
- After artifacts expire, run the complete release workflow again. Installer artifacts are retained for 14 days and diagnostic artifacts for 7 days.
- A source fix gets a new version/tag. Moving an existing release tag makes the published source and binary relationship ambiguous.

An incomplete release or explicit rebuild replaces only the versioned installer and its checksum. Replacement uploads delete the previous same-named assets first; an interrupted upload needs a retry. Other assets and release metadata are preserved. API authorization errors and server errors fail the workflow; only an HTTP 404 is treated as a missing release. See [GitHub release events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release) and [asset upload behavior](https://cli.github.com/manual/gh_release_upload).
