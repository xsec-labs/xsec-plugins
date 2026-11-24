#!/usr/bin/env python3
"""Decide which registered plugins have an unpublished version on their main branch.

Every plugin releases from the single ``main`` branch of its source repository.
``release-plugins.yml`` runs this planner whenever a plugin repository reports a
new main commit (and once a day as a safety net), then publishes each pending
plugin through ``publish.yml``.

A plugin is pending when its main head

* is not the source commit of the plugin's latest published release, and
* declares a version that has not been published yet and is newer than every
  published version.

A commit that does not change the version is skipped on purpose: a version
identifies exactly one immutable package, so documentation or CI commits on
main must not republish it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

REGISTRY_PATH = ".xsec-factory/official-registry.json"
SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


class PlanError(Exception):
    pass


def parse_version(value: str) -> tuple[int, int, int, tuple[tuple[int, object], ...]]:
    """Return a sortable SemVer key. A release sorts after its own pre-releases."""

    match = VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise PlanError(f"{value!r} is not a SemVer version")
    pre = match.group(4)
    if pre is None:
        pre_key: tuple[tuple[int, object], ...] = ((2, 0),)
    else:
        pre_key = tuple((0, int(part)) if part.isdecimal() else (1, part) for part in pre.split("."))
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), pre_key


def read_json(path: Path) -> object:
    with path.open("rb") as handle:
        return json.load(handle)


def published_state(root: Path, plugin_id: str) -> tuple[str | None, set[str]]:
    """Return the source SHA of the latest published release and every published version."""

    evidence_path = root / ".xsec-factory" / "official-publications" / f"{plugin_id}.json"
    last_sha: str | None = None
    if evidence_path.is_file():
        events = read_json(evidence_path).get("events", [])  # type: ignore[union-attr]
        for event in events:
            source = event.get("source") if isinstance(event, dict) else None
            if isinstance(source, dict) and isinstance(source.get("sha"), str):
                last_sha = source["sha"]
    releases_path = root / ".xsec-factory" / "snapshots" / plugin_id / ".xsec-market" / "releases.json"
    versions: set[str] = set()
    if releases_path.is_file():
        for release in read_json(releases_path).get("releases", []):  # type: ignore[union-attr]
            if isinstance(release, dict) and isinstance(release.get("version"), str):
                versions.add(release["version"])
    return last_sha, versions


def plan(
    root: Path,
    *,
    resolve_head: Callable[[str, str], str],
    read_version: Callable[[str, str, str], str],
    plugin_id: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Classify every active registered plugin (or just ``plugin_id``)."""

    registry = read_json(root / REGISTRY_PATH)
    pending: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    seen = False
    for entry in registry["plugins"]:  # type: ignore[index]
        current_id = entry["pluginId"]
        if plugin_id is not None and current_id != plugin_id:
            continue
        seen = True
        if entry.get("status") != "active":
            skipped.append({"pluginId": current_id, "reason": "not-active"})
            continue
        source = entry["source"]
        repository = source["repository"]
        ref = source["refs"]["beta"]
        manifest_path = (PurePosixPath(source["path"]) / "plugin.json").as_posix()
        try:
            head = resolve_head(repository, ref)
        except PlanError as error:
            skipped.append({"pluginId": current_id, "reason": f"head-unavailable: {error}"})
            continue
        if not SHA_PATTERN.fullmatch(head):
            skipped.append({"pluginId": current_id, "reason": "head-unavailable: not a commit SHA"})
            continue
        last_sha, published_versions = published_state(root, current_id)
        if head == last_sha:
            skipped.append({"pluginId": current_id, "reason": "up-to-date"})
            continue
        try:
            version = read_version(repository, head, manifest_path)
            candidate = parse_version(version)
        except PlanError as error:
            skipped.append({"pluginId": current_id, "reason": f"version-unreadable: {error}"})
            continue
        if version in published_versions:
            skipped.append({"pluginId": current_id, "reason": f"version-not-bumped: {version}"})
            continue
        newest = max((parse_version(item) for item in published_versions), default=None)
        if newest is not None and candidate < newest:
            skipped.append({"pluginId": current_id, "reason": f"version-older-than-published: {version}"})
            continue
        pending.append(
            {"pluginId": current_id, "repository": repository, "ref": ref, "sha": head, "version": version}
        )
    if plugin_id is not None and not seen:
        raise PlanError(f"{plugin_id} is not registered")
    return {"pending": pending, "skipped": skipped}


def git_resolve_head(token: str | None) -> Callable[[str, str], str]:
    def resolve(repository: str, ref: str) -> str:
        url = f"https://github.com/{repository}.git"
        command = ["git", "-c", "credential.helper=", "-c", "http.followRedirects=false"]
        if token:
            import base64

            header = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            command += ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {header}"]
        command += ["ls-remote", url, ref]
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_CONFIG")}
        env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120, check=False)
        if result.returncode != 0:
            raise PlanError(f"git ls-remote failed for {repository}")
        lines = [line for line in result.stdout.splitlines() if line.endswith(f"\t{ref}")]
        if len(lines) != 1:
            raise PlanError(f"{repository} has no {ref}")
        return lines[0].split("\t", 1)[0]

    return resolve


def http_read_version(token: str | None) -> Callable[[str, str, str], str]:
    def read(repository: str, sha: str, manifest_path: str) -> str:
        request = urllib.request.Request(f"https://raw.githubusercontent.com/{repository}/{sha}/{manifest_path}")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
                manifest = json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
            raise PlanError(f"cannot read {manifest_path} at {sha[:12]}: {error}") from error
        version = manifest.get("version") if isinstance(manifest, dict) else None
        if not isinstance(version, str):
            raise PlanError(f"{manifest_path} at {sha[:12]} has no version")
        return version

    return read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--plugin-id", help="Only consider this registered plugin")
    arguments = parser.parse_args(argv)
    token = os.environ.get("SOURCE_TOKEN") or None
    try:
        result = plan(
            arguments.root,
            resolve_head=git_resolve_head(token),
            read_version=http_read_version(token),
            plugin_id=arguments.plugin_id,
        )
    except PlanError as error:
        print(f"release planner failed: {error}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
