"""Validate release versions and generate build metadata without editing sources."""

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path


def read_metadata(root: Path, release_tag: str = "") -> dict[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+|\.post\d+|\.dev\d+)?", version):
        raise ValueError("Use a version such as 1.2.3 or 1.2.3rc1 in pyproject.toml")
    module = ast.parse((root / "src" / "narruvo" / "__init__.py").read_text(encoding="utf-8"))
    app_version = next(
        (ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
         and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)),
        None,
    )
    if app_version != version:
        raise ValueError(f"Version mismatch: pyproject.toml is {version}, narruvo.__version__ is {app_version}")
    if release_tag and release_tag != f"v{version}":
        raise ValueError(f"Release tag {release_tag!r} must match project version v{version}")
    numbers = tuple(int(part) for part in re.match(r"\d+\.\d+\.\d+", version).group().split("."))
    if any(part > 65535 for part in numbers):
        raise ValueError("Windows version components must be at most 65535")
    return {
        "version": version,
        "windows_version": ".".join(str(part) for part in (*numbers, 0)),
        "installer_name": f"Narruvo-{version}-windows-x64-setup.exe",
    }


def write_metadata(root: Path, output: Path, release_tag: str = "") -> dict[str, str]:
    metadata = read_metadata(root, release_tag)
    numbers = tuple(int(part) for part in metadata["windows_version"].split("."))
    version = metadata["version"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (output / "version-info.txt").write_text(
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r},\n"
        "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[StringFileInfo([StringTable('040904B0', [\n"
        "    StringStruct('CompanyName', 'Narruvo'),\n"
        "    StringStruct('FileDescription', 'Narruvo offline PDF audiobook reader'),\n"
        f"    StringStruct('FileVersion', {version!r}),\n"
        "    StringStruct('InternalName', 'Narruvo'),\n"
        "    StringStruct('OriginalFilename', 'Narruvo.exe'),\n"
        "    StringStruct('ProductName', 'Narruvo'),\n"
        f"    StringStruct('ProductVersion', {version!r})\n"
        "  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n"
        ")\n",
        encoding="utf-8",
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag", default="")
    parser.add_argument("--output-dir", type=Path, default=Path("build/windows"))
    args = parser.parse_args()
    try:
        metadata = write_metadata(Path(__file__).resolve().parents[1], args.output_dir, args.release_tag)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
