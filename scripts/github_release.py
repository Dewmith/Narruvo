"""Prepare and publish verified GitHub releases; used only by release CI."""

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.package_metadata import metadata_for_tag


log = logging.getLogger(__name__)


class GitHub:
    """Use the runner's GitHub CLI and GH_TOKEN without extra dependencies."""

    def __init__(self, repository: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise ValueError("Set GH_REPO to the owner/repository being released")
        self.repository = repository

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["gh", *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120, check=False,
        )

    def _get(
        self, endpoint: str, *, missing_ok: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        response = self._run("api", "--method", "GET", "--include", endpoint)
        headers, separator, body = response.stdout.replace("\r\n", "\n").partition("\n\n")
        status = re.match(r"HTTP/\S+\s+(\d{3})\b", headers)
        if response.returncode:
            if missing_ok and status and status[1] == "404":
                return None
            raise RuntimeError(response.stderr.strip() or f"GitHub request failed: {endpoint}")
        if not separator or not status or status[1] != "200":
            raise RuntimeError(f"Unexpected GitHub response for {endpoint}")
        result = json.loads(body)
        if not isinstance(result, (dict, list)):
            raise RuntimeError(f"Expected a GitHub object or array for {endpoint}")
        return result

    def _command(self, *arguments: str) -> None:
        response = self._run(*arguments)
        if response.returncode:
            raise RuntimeError(response.stderr.strip() or "GitHub release command failed")

    def require_tag(self, tag: str) -> None:
        self._get(f"repos/{self.repository}/git/ref/tags/{quote(tag, safe='')}")

    def get_release(self, tag: str) -> dict[str, Any] | None:
        release = self._get(
            f"repos/{self.repository}/releases/tags/{quote(tag, safe='')}", missing_ok=True,
        )
        if release is not None:
            if not isinstance(release, dict):
                raise RuntimeError("Expected a GitHub release object")
            return release
        # The tag endpoint only returns published releases. Authenticated listing
        # also exposes drafts to the publishing token, including interrupted runs.
        page = 1
        while True:
            candidates = self._get(f"repos/{self.repository}/releases?per_page=100&page={page}")
            if not isinstance(candidates, list):
                raise RuntimeError("Expected a GitHub release listing")
            for candidate in candidates:
                if candidate.get("tag_name") == tag:
                    return candidate
            if len(candidates) < 100:
                return None
            page += 1

    def create_draft(self, tag: str, *, prerelease: bool) -> None:
        arguments = [
            "release", "create", tag, "--repo", self.repository, "--verify-tag",
            "--title", f"Narruvo {tag}", "--draft", "--generate-notes",
        ]
        if prerelease:
            arguments.append("--prerelease")
        self._command(*arguments)

    def upload(self, tag: str, installer: Path, checksum: Path) -> None:
        self._command(
            "release", "upload", tag, str(installer), str(checksum),
            "--repo", self.repository, "--clobber",
        )

    def publish_draft(self, tag: str) -> None:
        self._command("release", "edit", tag, "--repo", self.repository, "--draft=false")


def resolve_tag(event_name: str, event: dict[str, Any], ref: str, input_tag: str) -> str | None:
    """Normalize supported triggers; deleted tags deliberately have no target."""
    if event_name == "push":
        if event.get("deleted"):
            return None
        if not ref.startswith("refs/tags/"):
            raise ValueError("Release pushes must target a version tag")
        tag = ref.removeprefix("refs/tags/")
    elif event_name == "release":
        tag = event.get("release", {}).get("tag_name", "")
    elif event_name == "workflow_dispatch":
        tag = input_tag
    else:
        raise ValueError(f"Unsupported release event: {event_name}")
    metadata_for_tag(tag)
    return tag


def is_prerelease(tag: str) -> bool:
    version = metadata_for_tag(tag)["version"]
    return re.search(r"(?:a|b|rc|\.dev)[0-9]+$", version) is not None


def assets_complete(release: dict[str, Any], tag: str) -> bool:
    name = metadata_for_tag(tag)["installer_name"]
    uploaded = {
        asset.get("name") for asset in release.get("assets", [])
        if asset.get("state") == "uploaded" and asset.get("size", 0) > 0
    }
    return {name, f"{name}.sha256"}.issubset(uploaded)


def require_mutable(release: dict[str, Any]) -> None:
    if release.get("immutable"):
        raise RuntimeError(
            "This published release is immutable and cannot accept installer assets. "
            "Keep release immutability disabled for release-first publication, "
            "or use a new tag so assets can be uploaded to a draft before publication."
        )


def prepare_release(github: GitHub, tag: str, *, rebuild: bool = False) -> bool:
    """Return whether packaging is needed; manual dispatch explicitly rebuilds."""
    metadata_for_tag(tag)
    github.require_tag(tag)
    release = github.get_release(tag)
    if release is not None:
        if not rebuild and not release["draft"] and assets_complete(release, tag):
            log.info("%s already has its installer and checksum; skipping duplicate build", tag)
            return False
        require_mutable(release)
    log.info("Building verified Windows assets for %s", tag)
    return True


def verify_assets(directory: Path, tag: str) -> tuple[Path, Path]:
    """Require exactly the two expected assets and verify their SHA-256 locally."""
    installer = directory / metadata_for_tag(tag)["installer_name"]
    checksum = installer.with_name(f"{installer.name}.sha256")
    files = [path for path in directory.rglob("*") if path.is_file()]
    if len(files) != 2 or not installer.is_file() or not checksum.is_file():
        raise ValueError("Expected exactly the versioned installer and its checksum")
    with installer.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    expected = f"{digest}  {installer.name}"
    if checksum.read_text(encoding="utf-8").rstrip("\r\n") != expected:
        raise ValueError("Installer checksum does not match")
    return installer, checksum


def publish_release(github: GitHub, tag: str, directory: Path, *, rebuild: bool = False) -> None:
    """Upload verified assets, preserving metadata, and publish a completed draft."""
    installer, checksum = verify_assets(directory, tag)
    github.require_tag(tag)
    release = github.get_release(tag)
    if release is None:
        try:
            github.create_draft(tag, prerelease=is_prerelease(tag))
        except RuntimeError:
            # A person may have created the release while this build was running.
            release = github.get_release(tag)
            if release is None:
                raise
        else:
            release = github.get_release(tag)
        if release is None:
            raise RuntimeError("The new draft release could not be retrieved")
    if not rebuild and not release["draft"] and assets_complete(release, tag):
        log.info("%s already has both release assets; leaving them in place", tag)
        return
    require_mutable(release)
    github.upload(tag, installer, checksum)
    release = github.get_release(tag)
    if release is None or not assets_complete(release, tag):
        raise RuntimeError("Both release assets must finish uploading before publication")
    if release["draft"]:
        github.publish_draft(tag)
    log.info("Published installer and checksum for %s", tag)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "publish"))
    parser.add_argument("--repo", default=os.environ.get("GH_REPO", ""))
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG", ""))
    parser.add_argument("--assets-dir", type=Path, default=Path("release-assets"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        rebuild = event_name == "workflow_dispatch"
        if args.command == "prepare":
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            tag = resolve_tag(event_name, event, os.environ.get("GITHUB_REF", ""), args.tag)
            should_build = tag is not None and prepare_release(GitHub(args.repo), tag, rebuild=rebuild)
            outputs = {"tag": tag or "", "should_build": str(should_build).lower()}
            if output_path := os.environ.get("GITHUB_OUTPUT"):
                with Path(output_path).open("a", encoding="utf-8") as output:
                    output.writelines(f"{key}={value}\n" for key, value in outputs.items())
            print(json.dumps(outputs))
        else:
            publish_release(GitHub(args.repo), args.tag, args.assets_dir, rebuild=rebuild)
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
