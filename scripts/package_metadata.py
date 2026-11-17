"""Synchronize release versions on request and generate validated build metadata."""

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path


_VERSION = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*)|\.(?:post|dev)(?:0|[1-9][0-9]*))?"
)


def _version_metadata(version: object) -> dict[str, str]:
    if not isinstance(version, str) or (match := _VERSION.fullmatch(version)) is None:
        raise ValueError("Use a version such as 1.2.3 or 1.2.3rc1, without leading zeroes")
    numbers = tuple(int(part) for part in match.group(1, 2, 3))
    if any(part > 65535 for part in numbers):
        raise ValueError("Windows version components must be at most 65535")
    return {
        "version": version,
        "windows_version": ".".join(str(part) for part in (*numbers, 0)),
        "installer_name": f"Narruvo-{version}-windows-x64-setup.exe",
    }


def metadata_for_tag(release_tag: str) -> dict[str, str]:
    """Validate a release tag without reading or changing the source versions."""
    if not release_tag.startswith("v"):
        raise ValueError("Use a release tag such as v1.2.3 or v1.2.3rc1")
    return _version_metadata(release_tag[1:])


def _metadata_from_sources(project_source: str, package_source: str, release_tag: str) -> dict[str, str]:
    version = tomllib.loads(project_source)["project"]["version"]
    metadata = _version_metadata(version)
    module = ast.parse(package_source)
    app_version = next(
        (ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
         and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)),
        None,
    )
    if app_version != version:
        raise ValueError(f"Version mismatch: pyproject.toml is {version}, narruvo.__version__ is {app_version}")
    if release_tag and release_tag != f"v{version}":
        raise ValueError(f"Release tag {release_tag!r} must match project version v{version}")
    return metadata


def read_metadata(root: Path, release_tag: str = "") -> dict[str, str]:
    return _metadata_from_sources(
        (root / "pyproject.toml").read_text(encoding="utf-8"),
        (root / "src" / "narruvo" / "__init__.py").read_text(encoding="utf-8"),
        release_tag,
    )


def _replace_assignment(source: str, name: str, version: str) -> str:
    updated, count = re.subn(
        rf"(?m)^([ \t]*{re.escape(name)}[ \t]*=[ \t]*)(['\"])[^\r\n]*?\2",
        lambda match: f"{match.group(1)}{match.group(2)}{version}{match.group(2)}",
        source,
    )
    if count != 1:
        raise ValueError(f"Expected exactly one literal {name} assignment")
    return updated


def sync_version(root: Path, release_tag: str) -> None:
    """Stamp both source versions from a tag before installing the Python package.

    Validate the tag and both proposed files before writing either file. Only the
    build checkout is changed; this function never creates commits or moves tags.
    """
    version = metadata_for_tag(release_tag)["version"]
    project_path = root / "pyproject.toml"
    package_path = root / "src" / "narruvo" / "__init__.py"
    project_source = project_path.read_bytes().decode("utf-8")
    package_source = package_path.read_bytes().decode("utf-8")
    project_section = re.search(
        r"(?ms)^[ \t]*\[project\][^\r\n]*\r?\n(?P<fields>.*?)(?=^[ \t]*\[|\Z)",
        project_source,
    )
    if project_section is None:
        raise ValueError("Expected a [project] section in pyproject.toml")
    fields = _replace_assignment(project_section.group("fields"), "version", version)
    updated_project = (
        project_source[:project_section.start("fields")] + fields
        + project_source[project_section.end("fields"):]
    )
    updated_package = _replace_assignment(package_source, "__version__", version)
    _metadata_from_sources(updated_project, updated_package, release_tag)
    if updated_project != project_source:
        project_path.write_text(updated_project, encoding="utf-8", newline="")
    if updated_package != package_source:
        package_path.write_text(updated_package, encoding="utf-8", newline="")


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
    parser.add_argument(
        "--sync-version", action="store_true",
        help="Set both source versions from --release-tag before generating metadata; run before pip install",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("build/windows"))
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[1]
        if args.sync_version:
            sync_version(root, args.release_tag)
        metadata = write_metadata(root, args.output_dir, args.release_tag)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(metadata))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
