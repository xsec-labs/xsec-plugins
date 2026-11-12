#!/usr/bin/env python3
"""Stage Factory output, including release files a snapshot's own .gitignore hides.

Snapshots are copies of plugin source trees and keep their `.gitignore`.  A
source repository may ignore its local build output, for example
`*.xsec-plugin`, which is exactly what the Factory writes below the snapshot's
`.xsec-market/artifacts`.  A plain `git add -A` then commits `releases.json`
without the archives it points at.  This helper stages the requested paths and
then force-stages every snapshot `.xsec-market` directory, and fails if any file
below one is still left out of the index.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SNAPSHOT_ROOT = Path(".xsec-factory") / "snapshots"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def market_directories(root: Path) -> list[str]:
    snapshots = root / SNAPSHOT_ROOT
    if not snapshots.is_dir():
        return []
    return sorted(
        (SNAPSHOT_ROOT / plugin.name / ".xsec-market").as_posix()
        for plugin in snapshots.iterdir()
        if plugin.is_dir() and (plugin / ".xsec-market").is_dir()
    )


def stage(root: Path, paths: list[str]) -> list[str]:
    git(root, "add", "-A", "--", *paths)
    markets = market_directories(root)
    if markets:
        git(root, "add", "-A", "--force", "--", *markets)
        left_out = git(root, "ls-files", "--others", "--", *markets).splitlines()
        if left_out:
            raise SystemExit(
                "Factory release files were not staged: " + ", ".join(sorted(left_out))
            )
    return markets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    stage(Path.cwd(), args.paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
