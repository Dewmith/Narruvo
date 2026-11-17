# Set up development

## Supported environment

Application development targets **Python 3.12 x64** on **Windows 10 version 1809 or later, or Windows 11**. Use the exact runtime and test versions in [pyproject.toml](https://github.com/Dewmith/Text2Voice/blob/main/pyproject.toml).

| Component | Pinned version |
| --- | --- |
| PySide6 | 6.10.3 |
| PyMuPDF | 1.26.7 |
| kokoro-onnx | 0.6.1 |
| NumPy | 2.5.5 |
| CPU ONNX Runtime | 1.32.0 |
| SoundFile | 0.13.1 |
| phonemizer | 3.6.0 |
| pytest / pytest-qt | 9.2.0 / 4.5.0 |

Documentation has its own Python environment and can be built on Windows or Linux; see [maintaining the docs](maintaining-docs.md).

## Clone and install

From PowerShell:

```powershell
git clone https://github.com/Dewmith/Text2Voice.git
Set-Location Text2Voice
.\scripts\setup.ps1
.\scripts\run.ps1
```

`setup.ps1` discovers Python 3.12 x64, creates `.venv`, and installs the project with test dependencies. It checks the Python launcher, PATH, uv-managed installations, and the usual Python 3.12 installation directory. It leaves global packages alone and does not download models.

If automatic discovery fails, specify a Python executable:

```powershell
.\scripts\setup.ps1 -Python 'C:\path\to\Python312\python.exe'
```

If PowerShell script execution is restricted, use a process-local override:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

### Manual setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m voiceleaf
```

The module entry point calls `multiprocessing.freeze_support()` before importing the GUI. Keep that ordering when changing startup or packaging.

## First development checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\scripts\run.ps1 -SmokeTest
.\scripts\run.ps1 -Pdf 'C:\Books\Sample.pdf'
```

Ordinary tests generate small fixture PDFs and do not require models. The smoke test opens the window briefly without the first-run setup dialog.

## Isolate development data

Use a separate data directory when reproducing cache, library, or model-setup behavior:

```powershell
$env:VOICELEAF_DATA_DIR = Join-Path $PWD '.artifacts\dev-data'
.\scripts\run.ps1
Remove-Item Env:VOICELEAF_DATA_DIR
```

{py:class}`voiceleaf.config.AppPaths` discovers this override. All settings, library records, downloaded models, generated audio, and logs then belong to that directory. Imported PDF originals remain at their existing paths.

## Models for development

Choose the app's explicit setup dialog to download or select the two model files. For repeatable integration checks, reuse existing files through `VOICELEAF_TEST_MODELS`; the tests do not download anything.

An explicit CLI downloader is also available:

```powershell
.\.venv\Scripts\python.exe scripts\download_models.py
# Accept the displayed approximately 354 MB download explicitly:
.\.venv\Scripts\python.exe scripts\download_models.py --yes
```

The default destination is `%LOCALAPPDATA%\VoiceLeaf\models`. The downloader verifies the manifest's byte counts and SHA-256 digests before installing files. A `--data-dir` argument selects another application data root. eSpeak resources come from the installed package; no spaCy or NLTK model download is needed.

Model files, PDFs, generated audio, databases, and logs stay outside commits. The [testing guide](testing.md) describes opt-in synthesis and native multimedia checks.

## Repository map

| Location | Responsibility |
| --- | --- |
| `src/voiceleaf/` | Domain records, processing, persistence, and controllers |
| `src/voiceleaf/ui/` | Qt window, views, dialogs, controls, and theme |
| `tests/` | Ordinary tests and opt-in real-model integration tests |
| `scripts/` | Environment setup, launch, model download, and installer verification |
| `packaging/` | PyInstaller bundle and Inno Setup installer definitions |
| `.github/workflows/` | Windows CI, releases, and documentation publication |
| `docs/` | This handbook and documentation configuration |

Continue with [architecture and data flow](architecture.md).
