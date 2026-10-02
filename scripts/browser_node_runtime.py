#!/usr/bin/env python3
"""Fetch and extract the pinned official Node runtime for browser artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

from native_sidecars import BROWSER_NODE_DISTRIBUTIONS, BROWSER_NODE_VERSION


NODE_BASE_URL = f"https://nodejs.org/dist/{BROWSER_NODE_VERSION}/"
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_NODE_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


def download_archive(platform: str, cache_root: Path) -> Path:
    filename, expected_digest = distribution(platform)
    cache_root.mkdir(parents=True, exist_ok=True)
    archive = cache_root / filename
    if archive.exists() or os.path.lexists(archive):
        verify_archive(archive, expected_digest)
        return archive
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache_root, prefix=".node-download-", delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            total = 0
            with urlopen(NODE_BASE_URL + filename, timeout=60) as response:
                while chunk := response.read(CHUNK_BYTES):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError("official Node archive exceeds the download limit")
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected_digest:
            raise ValueError(f"official Node archive digest mismatch for {filename}")
        os.replace(temporary, archive)
        temporary = None
        verify_archive(archive, expected_digest)
        return archive
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def extract_node(archive: Path, platform: str, destination: Path) -> Path:
    filename, digest = distribution(platform)
    verify_archive(archive, digest)
    member = node_member(filename, platform)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise ValueError(f"browser Node destination already exists: {destination}")
    if filename.endswith(".zip"):
        write_zip_member(archive, member, destination)
    else:
        write_tar_member(archive, member, destination)
    if destination.stat().st_size > MAX_NODE_BYTES:
        raise ValueError("official Node executable exceeds the file limit")
    if platform != "windows-x86_64":
        destination.chmod(0o755)
    version = subprocess.run(
        [str(destination), "--version"], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()
    if version != BROWSER_NODE_VERSION:
        raise ValueError(f"official Node executable reports {version}, expected {BROWSER_NODE_VERSION}")
    return destination


def distribution(platform: str) -> tuple[str, str]:
    try:
        return BROWSER_NODE_DISTRIBUTIONS[platform]
    except KeyError as error:
        raise ValueError(f"unsupported browser Node platform: {platform}") from error


def node_member(filename: str, platform: str) -> str:
    archive_root = filename.removesuffix(".tar.gz").removesuffix(".tar.xz").removesuffix(".zip")
    if platform == "windows-x86_64":
        return f"{archive_root}/node.exe"
    return f"{archive_root}/bin/node"


def verify_archive(archive: Path, expected_digest: str) -> None:
    metadata = archive.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size == 0 or metadata.st_size > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"official Node archive must be a regular file within the size limit: {archive}")
    if file_sha256(archive) != expected_digest:
        raise ValueError(f"official Node archive digest mismatch: {archive}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def write_tar_member(archive: Path, member_name: str, destination: Path) -> None:
    with tarfile.open(archive, mode="r:*") as source:
        member = source.getmember(member_name)
        if not member.isfile() or member.size <= 0 or member.size > MAX_NODE_BYTES:
            raise ValueError("official Node archive contains an invalid executable entry")
        content = source.extractfile(member)
        if content is None:
            raise ValueError("official Node executable cannot be read from the archive")
        with content, destination.open("xb") as output:
            shutil.copyfileobj(content, output, CHUNK_BYTES)


def write_zip_member(archive: Path, member_name: str, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        member = source.getinfo(member_name)
        mode = member.external_attr >> 16
        if stat.S_IFMT(mode) not in {0, stat.S_IFREG} or not 0 < member.file_size <= MAX_NODE_BYTES:
            raise ValueError("official Node archive contains an invalid executable entry")
        with source.open(member) as content, destination.open("xb") as output:
            shutil.copyfileobj(content, output, CHUNK_BYTES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted(BROWSER_NODE_DISTRIBUTIONS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "xsec-browser-node")
    args = parser.parse_args()
    archive = download_archive(args.platform, args.cache_dir)
    executable = extract_node(archive, args.platform, args.output)
    print(f"Prepared Node {BROWSER_NODE_VERSION}: {executable} sha256={file_sha256(executable)}")


if __name__ == "__main__":
    main()
