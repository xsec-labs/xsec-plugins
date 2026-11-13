"""Fail when a plugin submodule pointer is not the head of its Beta branch.

Plugins are released from their Beta branch, so each gitlink recorded in this
repository must move with every Beta commit of its plugin. The check reads the
branch of each submodule from .gitmodules, resolves its current head with
git ls-remote, and compares it with the gitlink recorded in HEAD.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def submodule_branches(root: Path) -> list[tuple[str, str, str]]:
    """Return (path, url, branch) for each submodule that tracks a branch."""
    output = subprocess.run(
        ["git", "config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.(path|url|branch)$"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    entries: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        key, value = line.split(" ", 1)
        name, field = key[len("submodule.") :].rsplit(".", 1)
        entries.setdefault(name, {})[field] = value
    return [
        (fields["path"], fields["url"], fields["branch"])
        for fields in entries.values()
        if "path" in fields and "url" in fields and "branch" in fields
    ]


def recorded_pointer(root: Path, path: str) -> str:
    """Return the commit that HEAD records for the submodule at path."""
    output = subprocess.run(
        ["git", "ls-tree", "HEAD", "--", path],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if len(output) < 3 or output[1] != "commit" or not SHA_RE.match(output[2]):
        raise ValueError(f"{path} is not a submodule gitlink in HEAD")
    return output[2]


def branch_head(url: str, branch: str) -> str:
    """Return the current commit of a remote branch."""
    lines = subprocess.run(
        ["git", "ls-remote", url, f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if not lines or not SHA_RE.match(lines[0]):
        raise ValueError(f"{url} has no {branch} branch")
    return lines[0]


def mismatches(pointers: dict[str, str], heads: dict[str, str]) -> list[str]:
    """Describe each submodule whose recorded pointer is not its branch head."""
    problems = []
    for path in sorted(heads):
        recorded = pointers.get(path)
        if recorded != heads[path]:
            problems.append(f"{path}: pointer {recorded} is not the Beta head {heads[path]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    entries = submodule_branches(root)
    if not entries:
        print("error: no branch-tracking submodules found in .gitmodules", file=sys.stderr)
        return 1
    pointers = {path: recorded_pointer(root, path) for path, _, _ in entries}
    heads = {path: branch_head(url, branch) for path, url, branch in entries}
    problems = mismatches(pointers, heads)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("Bump each stale plugin submodule pointer to its Beta head in the same change.", file=sys.stderr)
        return 1
    print(f"{len(entries)} plugin submodule pointers match their Beta heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
