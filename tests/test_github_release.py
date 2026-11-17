import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import github_release as releases
from scripts.package_metadata import metadata_for_tag


TAG = "v0.4.0"


def release_record(tag: str = TAG, *, draft: bool = False, complete: bool = False,
                   immutable: bool = False, prerelease: bool = False) -> dict[str, Any]:
    name = metadata_for_tag(tag)["installer_name"]
    return {
        "name": "A maintainer's release title", "body": "Keep these release notes.",
        "draft": draft, "immutable": immutable, "prerelease": prerelease,
        "assets": [
            {"name": filename, "state": "uploaded", "size": 100}
            for filename in (name, f"{name}.sha256")
        ] if complete else [],
    }


class MemoryGitHub(releases.GitHub):
    def __init__(self, release: dict[str, Any] | None = None) -> None:
        super().__init__("example/Narruvo")
        self.release = copy.deepcopy(release)
        self.calls: list[tuple] = []
        self.tag_available = True
        self.fail_upload = False
        self.fail_create_after_creation = False

    def require_tag(self, tag: str) -> None:
        self.calls.append(("tag", tag))
        if not self.tag_available:
            raise RuntimeError("Tag does not exist")

    def get_release(self, tag: str) -> dict[str, Any] | None:
        self.calls.append(("get", tag))
        return copy.deepcopy(self.release)

    def create_draft(self, tag: str, *, prerelease: bool) -> None:
        self.calls.append(("create", tag, prerelease))
        self.release = release_record(tag, draft=True, prerelease=prerelease)
        if self.fail_create_after_creation:
            raise RuntimeError("Release was created concurrently")

    def upload(self, tag: str, installer: Path, checksum: Path) -> None:
        self.calls.append(("upload", tag))
        assert self.release is not None
        assets = {asset["name"]: asset for asset in self.release["assets"]}
        for file in (installer, checksum):
            assets[file.name] = {"name": file.name, "state": "uploaded", "size": file.stat().st_size}
            self.release["assets"] = list(assets.values())
            if self.fail_upload:
                raise RuntimeError("Interrupted upload")

    def publish_draft(self, tag: str) -> None:
        self.calls.append(("publish", tag))
        assert self.release is not None
        self.release["draft"] = False


def make_assets(root: Path, tag: str = TAG) -> Path:
    directory = root / "assets"
    directory.mkdir()
    installer = directory / metadata_for_tag(tag)["installer_name"]
    content = b"A test installer, not a real executable."
    installer.write_bytes(content)
    installer.with_name(f"{installer.name}.sha256").write_text(
        f"{hashlib.sha256(content).hexdigest()}  {installer.name}\n", encoding="utf-8",
    )
    return directory


@pytest.mark.parametrize("tag,prerelease", [
    ("v0.4.0", False), ("v0.4.0.post1", False), ("v0.4.0a0", True),
    ("v0.4.0b2", True), ("v0.4.0rc1", True), ("v0.4.0.dev0", True),
])
def test_tag_version_decides_new_release_type(tag, prerelease):
    assert releases.is_prerelease(tag) is prerelease


@pytest.mark.parametrize("event_name,event,ref,input_tag", [
    ("push", {}, "refs/tags/v0.4.0", "main"),
    ("release", {"release": {"tag_name": TAG}}, "refs/heads/main", "v9.9.9"),
    ("workflow_dispatch", {}, "refs/heads/main", TAG),
])
def test_each_trigger_resolves_its_own_tag(event_name, event, ref, input_tag):
    assert releases.resolve_tag(event_name, event, ref, input_tag) == TAG


def test_deleted_tags_are_ignored():
    assert releases.resolve_tag("push", {"deleted": True}, "refs/tags/v0.4.0", "") is None


@pytest.mark.parametrize("event_name,event,ref,input_tag", [
    ("push", {}, "refs/heads/main", ""),
    ("release", {"release": {}}, "refs/heads/main", TAG),
    ("workflow_dispatch", {}, "refs/heads/main", ""),
    ("pull_request", {}, "refs/heads/main", TAG),
])
def test_non_release_events_cannot_fall_back_to_an_unrelated_tag(event_name, event, ref, input_tag):
    with pytest.raises(ValueError):
        releases.resolve_tag(event_name, event, ref, input_tag)


@pytest.mark.parametrize("tag", ["", "0.4.0", "v01.4.0", "v0.4.0-beta.1", "v0.4.70000", "v0.4.0\n"])
def test_invalid_tags_never_contact_github(tag):
    github = MemoryGitHub()
    with pytest.raises(ValueError):
        releases.prepare_release(github, tag)
    assert not github.calls


def test_a_missing_release_can_build_but_a_missing_tag_cannot():
    github = MemoryGitHub()
    assert releases.prepare_release(github, TAG)
    assert github.release is None
    github.tag_available = False
    with pytest.raises(RuntimeError, match="Tag does not exist"):
        releases.prepare_release(github, TAG)


@pytest.mark.parametrize("immutable", [False, True])
def test_completed_published_releases_skip_automatic_duplicate_builds(immutable):
    github = MemoryGitHub(release_record(complete=True, immutable=immutable))
    assert not releases.prepare_release(github, TAG)
    assert not any(call[0] in {"create", "upload", "publish"} for call in github.calls)


def test_manual_dispatch_explicitly_rebuilds_completed_mutable_release():
    github = MemoryGitHub(release_record(complete=True))
    assert releases.prepare_release(github, TAG, rebuild=True)


@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("defect", ["missing", "empty", "uploading"])
def test_incomplete_assets_need_a_build(draft, defect):
    record = release_record(draft=draft, complete=True)
    if defect == "missing":
        record["assets"].pop()
    elif defect == "empty":
        record["assets"][0]["size"] = 0
    else:
        record["assets"][0]["state"] = "starter"
    assert releases.prepare_release(MemoryGitHub(record), TAG)


def test_completed_draft_is_resumed_instead_of_skipped():
    assert releases.prepare_release(MemoryGitHub(release_record(draft=True, complete=True)), TAG)


@pytest.mark.parametrize("complete,rebuild", [(False, False), (True, True)])
def test_immutable_releases_requiring_writes_fail_before_packaging(complete, rebuild):
    github = MemoryGitHub(release_record(complete=complete, immutable=True))
    with pytest.raises(RuntimeError, match="immutable"):
        releases.prepare_release(github, TAG, rebuild=rebuild)


@pytest.mark.parametrize("tag,prerelease", [(TAG, False), ("v0.4.0rc1", True)])
def test_new_release_is_published_only_after_both_verified_assets_are_uploaded(tmp_path, tag, prerelease):
    github = MemoryGitHub()
    directory = make_assets(tmp_path, tag)
    releases.publish_release(github, tag, directory)
    assert github.release is not None
    assert not github.release["draft"]
    assert github.release["prerelease"] is prerelease
    assert releases.assets_complete(github.release, tag)
    writes = [call[0] for call in github.calls if call[0] in {"create", "upload", "publish"}]
    assert writes == ["create", "upload", "publish"]
    assert not releases.prepare_release(github, tag)
    releases.publish_release(github, tag, directory)
    assert sum(call[0] == "upload" for call in github.calls) == 1


@pytest.mark.parametrize("draft", [False, True])
def test_existing_release_metadata_and_other_assets_are_preserved(tmp_path, draft):
    record = release_record(draft=draft, prerelease=True)
    extra = {"name": "release-information.txt", "state": "uploaded", "size": 10}
    record["assets"].append(extra)
    github = MemoryGitHub(record)
    releases.publish_release(github, TAG, make_assets(tmp_path))
    assert github.release is not None
    for key in ("name", "body", "prerelease"):
        assert github.release[key] == record[key]
    assert extra in github.release["assets"]
    assert not github.release["draft"]
    assert not any(call[0] == "create" for call in github.calls)
    assert sum(call[0] == "publish" for call in github.calls) == int(draft)


def test_manual_rebuild_can_replace_complete_assets(tmp_path):
    github = MemoryGitHub(release_record(complete=True))
    releases.publish_release(github, TAG, make_assets(tmp_path), rebuild=True)
    assert ("upload", TAG) in github.calls
    assert not any(call[0] in {"create", "publish"} for call in github.calls)


@pytest.mark.parametrize("defect", ["checksum", "missing", "extra", "wrong-version"])
def test_invalid_local_assets_cannot_create_or_modify_a_release(tmp_path, defect):
    directory = make_assets(tmp_path)
    installer = directory / metadata_for_tag(TAG)["installer_name"]
    if defect == "checksum":
        installer.write_bytes(b"Changed after verification")
    elif defect == "missing":
        installer.unlink()
    elif defect == "extra":
        (directory / "unexpected.txt").write_text("Must not be published")
    else:
        installer.rename(directory / "Narruvo-0.3.0-windows-x64-setup.exe")
    github = MemoryGitHub()
    with pytest.raises(ValueError):
        releases.publish_release(github, TAG, directory)
    assert not github.calls


def test_failed_upload_leaves_draft_unpublished_and_retry_finishes_it(tmp_path):
    directory = make_assets(tmp_path)
    github = MemoryGitHub()
    github.fail_upload = True
    with pytest.raises(RuntimeError, match="Interrupted upload"):
        releases.publish_release(github, TAG, directory)
    assert github.release is not None and github.release["draft"]
    assert not releases.assets_complete(github.release, TAG)
    assert not any(call[0] == "publish" for call in github.calls)
    assert releases.prepare_release(github, TAG)
    github.fail_upload = False
    releases.publish_release(github, TAG, directory)
    assert not github.release["draft"]
    assert releases.assets_complete(github.release, TAG)
    assert sum(call[0] == "create" for call in github.calls) == 1


def test_concurrent_release_creation_is_reused(tmp_path):
    github = MemoryGitHub()
    github.fail_create_after_creation = True
    releases.publish_release(github, TAG, make_assets(tmp_path))
    assert github.release is not None and not github.release["draft"]


@pytest.mark.parametrize("status,missing", [(404, True), (401, False), (403, False), (500, False)])
def test_only_http_404_means_a_release_is_missing(monkeypatch, status, missing):
    def command(arguments, **_kwargs):
        if missing and "/releases?" in arguments[-1]:
            return subprocess.CompletedProcess(arguments, 0, 'HTTP/2.0 200 OK\n\n[]', "")
        return subprocess.CompletedProcess(
            arguments, 1, f'HTTP/2.0 {status} Error\r\nContent-Type: application/json\r\n\r\n{{}}',
            f"GitHub HTTP {status}",
        )

    monkeypatch.setattr(releases.subprocess, "run", command)
    github = releases.GitHub("example/Narruvo")
    if missing:
        assert github.get_release(TAG) is None
    else:
        with pytest.raises(RuntimeError, match=str(status)):
            github.get_release(TAG)


def test_github_json_response_and_release_commands(monkeypatch):
    commands = []

    def command(arguments, **_kwargs):
        commands.append(arguments)
        return subprocess.CompletedProcess(
            arguments, 0, 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"draft": true}', "",
        )

    monkeypatch.setattr(releases.subprocess, "run", command)
    github = releases.GitHub("example/Narruvo")
    assert github.get_release(TAG) == {"draft": True}
    github.create_draft("v0.4.0rc1", prerelease=True)
    assert "--draft" in commands[-1] and "--verify-tag" in commands[-1]
    assert "--prerelease" in commands[-1]
    github.create_draft(TAG, prerelease=False)
    assert "--prerelease" not in commands[-1]
    github.publish_draft(TAG)
    assert commands[-1] == [
        "gh", "release", "edit", TAG, "--repo", "example/Narruvo", "--draft=false",
    ]


def test_draft_hidden_by_tag_endpoint_is_found_in_authenticated_listing(monkeypatch):
    draft = {**release_record(draft=True), "tag_name": TAG}

    def command(arguments, **_kwargs):
        if "/releases/tags/" in arguments[-1]:
            return subprocess.CompletedProcess(arguments, 1, 'HTTP/2.0 404 Not Found\n\n{}', "Not found")
        return subprocess.CompletedProcess(arguments, 0, f'HTTP/2.0 200 OK\n\n{json.dumps([draft])}', "")

    monkeypatch.setattr(releases.subprocess, "run", command)
    assert releases.GitHub("example/Narruvo").get_release(TAG) == draft


def test_draft_lookup_checks_later_pages(monkeypatch):
    draft = {**release_record(draft=True), "tag_name": TAG}
    endpoints = []

    def command(arguments, **_kwargs):
        endpoint = arguments[-1]
        endpoints.append(endpoint)
        if "/releases/tags/" in endpoint:
            return subprocess.CompletedProcess(arguments, 1, 'HTTP/2.0 404 Not Found\n\n{}', "Not found")
        candidates = [dict(draft, tag_name=f"v0.0.{i}") for i in range(100)] if endpoint.endswith("&page=1") else [draft]
        return subprocess.CompletedProcess(arguments, 0, f'HTTP/2.0 200 OK\n\n{json.dumps(candidates)}', "")

    monkeypatch.setattr(releases.subprocess, "run", command)
    assert releases.GitHub("example/Narruvo").get_release(TAG) == draft
    assert endpoints[-1].endswith("page=2")


def test_draft_listing_authorization_error_does_not_mean_missing_release(monkeypatch):
    def command(arguments, **_kwargs):
        status = 404 if "/releases/tags/" in arguments[-1] else 403
        return subprocess.CompletedProcess(arguments, 1, f'HTTP/2.0 {status} Error\n\n{{}}', f"HTTP {status}")

    monkeypatch.setattr(releases.subprocess, "run", command)
    with pytest.raises(RuntimeError, match="403"):
        releases.GitHub("example/Narruvo").get_release(TAG)


@pytest.mark.parametrize("event_name,should_build", [("push", "false"), ("workflow_dispatch", "true")])
def test_prepare_command_exports_build_decision_without_modifying_release(tmp_path, monkeypatch, event_name, should_build):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"deleted": False}), encoding="utf-8")
    output = tmp_path / "outputs.txt"
    github = MemoryGitHub(release_record(complete=True))
    monkeypatch.setattr(releases, "GitHub", lambda _repo: github)
    for key, value in {
        "GH_REPO": "example/Narruvo", "RELEASE_TAG": TAG, "GITHUB_EVENT_NAME": event_name,
        "GITHUB_REF": f"refs/tags/{TAG}", "GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(key, value)
    assert releases.main(["prepare"]) == 0
    assert output.read_text(encoding="utf-8") == f"tag={TAG}\nshould_build={should_build}\n"
    assert not any(call[0] in {"create", "upload", "publish"} for call in github.calls)
