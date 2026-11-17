"""Windows x64 application bundle. Build via scripts/build.ps1."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = []
binaries = []
hiddenimports = ["PySide6.QtMultimedia"]
for package in ("pymupdf", "onnxruntime", "espeakng_loader"):
    binaries += collect_dynamic_libs(package)
for package in ("kokoro_onnx", "phonemizer", "espeakng_loader"):
    datas += collect_data_files(package, excludes=["**/tests/**"])
    hiddenimports += collect_submodules(package, filter=lambda name: ".tests" not in name)
datas += copy_metadata("narruvo", recursive=True)

a = Analysis(
    [str(root / "src" / "narruvo" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(root / "packaging" / "windowed_streams.py")],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Narruvo",
    console=False,
    debug=False,
    strip=False,
    upx=False,
    version=str(root / "build" / "windows" / "version-info.txt"),
)
bundle = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Narruvo")
