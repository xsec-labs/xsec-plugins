"""Factory output staging keeps archives a snapshot's .gitignore would hide."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_factory_output  # noqa: E402


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


class StageFactoryOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "test")
        git(self.root, "config", "user.email", "test@example.invalid")
        self.snapshot = self.root / ".xsec-factory" / "snapshots" / "com.example.native"
        self.snapshot.mkdir(parents=True)
        # Like the binary-analysis source: its own build output is ignored.
        (self.snapshot / ".gitignore").write_text("*.xsec-plugin\n/.xsec-build/\n", encoding="utf-8")
        (self.snapshot / "plugin.json").write_text("{}\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def staged(self) -> set[str]:
        return set(git(self.root, "diff", "--cached", "--name-only").splitlines())

    def test_archives_ignored_by_the_snapshot_are_staged(self) -> None:
        market = self.snapshot / ".xsec-market"
        (market / "artifacts").mkdir(parents=True)
        (market / "releases.json").write_text("{}\n", encoding="utf-8")
        (market / "artifacts" / "a-linux-x86_64.xsec-plugin").write_bytes(b"zip")
        build = self.snapshot / ".xsec-build"
        build.mkdir()
        (build / "scratch.xsec-plugin").write_bytes(b"tmp")

        markets = stage_factory_output.stage(self.root, [".xsec-factory"])

        prefix = ".xsec-factory/snapshots/com.example.native/"
        self.assertEqual(markets, [prefix + ".xsec-market"])
        self.assertEqual(
            self.staged(),
            {
                prefix + ".xsec-market/releases.json",
                prefix + ".xsec-market/artifacts/a-linux-x86_64.xsec-plugin",
            },
        )

    def test_removed_archives_are_staged_as_deletions(self) -> None:
        archive = self.snapshot / ".xsec-market" / "artifacts" / "old.xsec-plugin"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"old")
        stage_factory_output.stage(self.root, [".xsec-factory"])
        git(self.root, "commit", "-q", "-m", "release")

        archive.unlink()
        stage_factory_output.stage(self.root, [".xsec-factory"])

        status = git(self.root, "diff", "--cached", "--name-status").splitlines()
        self.assertEqual(
            status,
            ["D\t.xsec-factory/snapshots/com.example.native/.xsec-market/artifacts/old.xsec-plugin"],
        )

    def test_a_tree_without_snapshots_is_staged_normally(self) -> None:
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        git(empty, "init", "-q")
        (empty / ".agents").mkdir()
        (empty / ".agents" / "marketplace.json").write_text("{}\n", encoding="utf-8")

        self.assertEqual(stage_factory_output.stage(empty, [".agents"]), [])
        self.assertEqual(
            git(empty, "diff", "--cached", "--name-only").splitlines(),
            [".agents/marketplace.json"],
        )


if __name__ == "__main__":
    unittest.main()
