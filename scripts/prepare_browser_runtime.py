#!/usr/bin/env python3
"""Materialize locked browser packages without pnpm's symlinked install tree."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Iterable


PACKAGES = ("cloakbrowser", "playwright-core")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-node-modules", required=True, type=Path)
    parser.add_argument("--destination-node-modules", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_node_modules.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("browser dependency source must be a directory")
    destination = args.destination_node_modules
    if destination.exists() or destination.is_symlink():
        raise ValueError("browser dependency destination already exists")
    destination.mkdir(parents=True)
    for name in PACKAGES:
        source_package = resolve_package(source / name, source, name)
        copy_package(source_package, destination / name, source, frozenset())
    return 0


def resolve_package(candidate: Path, source_root: Path, package_name: str) -> Path:
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(source_root):
        raise ValueError(f"browser package is outside the deployed dependency tree: {candidate}")
    manifest = json.loads((resolved / "package.json").read_text(encoding="utf-8"))
    if manifest.get("name") != package_name:
        raise ValueError(f"browser package name does not match its path: {candidate}")
    return resolved


def copy_package(source: Path, destination: Path, source_root: Path, ancestors: frozenset[Path]) -> None:
    if destination.exists():
        return
    validate_links(source, source_root)
    shutil.copytree(source, destination, symlinks=False, ignore=ignore_node_modules)
    next_ancestors = ancestors | {source}
    manifest = json.loads((source / "package.json").read_text(encoding="utf-8"))
    for key in ("dependencies", "optionalDependencies"):
        dependencies = manifest.get(key, {})
        if not isinstance(dependencies, dict):
            raise ValueError(f"invalid {key} in {source / 'package.json'}")
        for name in dependencies:
            linked = resolve_dependency(source, name, source_root)
            if linked is None:
                if key == "optionalDependencies":
                    continue
                raise ValueError(f"deployed browser dependency is missing: {name} for {source}")
            child = resolve_package(linked, source_root, name)
            if child not in next_ancestors:
                copy_package(child, destination / "node_modules" / name, source_root, next_ancestors)


def resolve_dependency(source: Path, name: str, source_root: Path) -> Path | None:
    directory = source
    while directory.is_relative_to(source_root):
        modules = directory if directory.name == "node_modules" else directory / "node_modules"
        candidate = modules / name
        if candidate.exists() or candidate.is_symlink():
            return candidate
        directory = directory.parent
    return None


def validate_links(source: Path, source_root: Path) -> None:
    for current, directories, names in os.walk(source, followlinks=False):
        if "node_modules" in directories:
            directories.remove("node_modules")
        for path in (Path(current) / name for name in (*directories, *names)):
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(source_root) or resolved == source or source in resolved.parents:
                    raise ValueError(f"browser package link escapes its locked deploy tree: {path}")


def ignore_node_modules(directory: str, names: Iterable[str]) -> set[str]:
    del directory
    return {"node_modules"} if "node_modules" in names else set()


if __name__ == "__main__":
    raise SystemExit(main())
