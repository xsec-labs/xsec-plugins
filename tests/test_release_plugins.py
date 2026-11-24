from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_plugins as planner  # noqa: E402

HEAD = "a" * 40
OLD = "b" * 40


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def make_root(root: Path, *, published: dict[str, tuple[str, list[str]]], status: str = "active") -> None:
    plugins = []
    for plugin_id, (last_sha, versions) in published.items():
        plugins.append(
            {
                "pluginId": plugin_id,
                "status": status,
                "source": {
                    "repository": f"acme/{plugin_id}",
                    "path": ".",
                    "refs": {"beta": "refs/heads/main", "stable": "refs/heads/main"},
                },
            }
        )
        write(
            root / ".xsec-factory" / "official-publications" / f"{plugin_id}.json",
            {"events": [{"source": {"sha": last_sha}}] if last_sha else []},
        )
        write(
            root / ".xsec-factory" / "snapshots" / plugin_id / ".xsec-market" / "releases.json",
            {"releases": [{"version": version} for version in versions]},
        )
    write(root / ".xsec-factory" / "official-registry.json", {"plugins": plugins})


class ReleasePlannerTests(unittest.TestCase):
    def run_plan(self, published, *, head=HEAD, version="1.2.0", plugin_id=None, status="active"):
        with tempfile.TemporaryDirectory(prefix="xsec-release-plan-") as directory:
            root = Path(directory)
            make_root(root, published=published, status=status)
            return planner.plan(
                root,
                resolve_head=lambda repository, ref: head,
                read_version=lambda repository, sha, path: version,
                plugin_id=plugin_id,
            )

    def test_new_version_on_a_new_commit_is_pending(self) -> None:
        result = self.run_plan({"p": (OLD, ["1.1.0"])})
        self.assertEqual([item["version"] for item in result["pending"]], ["1.2.0"])
        self.assertEqual(result["pending"][0]["sha"], HEAD)
        self.assertEqual(result["pending"][0]["ref"], "refs/heads/main")

    def test_published_head_is_up_to_date(self) -> None:
        result = self.run_plan({"p": (HEAD, ["1.2.0"])})
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["skipped"], [{"pluginId": "p", "reason": "up-to-date"}])

    def test_a_commit_without_a_version_bump_is_skipped(self) -> None:
        result = self.run_plan({"p": (OLD, ["1.2.0"])})
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["skipped"][0]["reason"], "version-not-bumped: 1.2.0")

    def test_a_version_older_than_the_newest_published_one_is_skipped(self) -> None:
        result = self.run_plan({"p": (OLD, ["1.1.0", "2.0.0"])})
        self.assertEqual(result["pending"], [])
        self.assertTrue(result["skipped"][0]["reason"].startswith("version-older-than-published"))

    def test_a_release_sorts_after_its_own_prerelease(self) -> None:
        result = self.run_plan({"p": (OLD, ["1.2.0-rc.1"])})
        self.assertEqual(len(result["pending"]), 1)

    def test_first_publication_has_no_history(self) -> None:
        result = self.run_plan({"p": (None, [])})
        self.assertEqual(len(result["pending"]), 1)

    def test_inactive_plugins_are_not_released(self) -> None:
        result = self.run_plan({"p": (OLD, ["1.1.0"])}, status="disabled")
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["skipped"], [{"pluginId": "p", "reason": "not-active"}])

    def test_an_unreadable_head_or_version_never_releases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-release-plan-") as directory:
            root = Path(directory)
            make_root(root, published={"p": (OLD, ["1.1.0"])})

            def no_head(repository: str, ref: str) -> str:
                raise planner.PlanError("down")

            result = planner.plan(root, resolve_head=no_head, read_version=lambda *_: "1.2.0")
            self.assertEqual(result["pending"], [])
            self.assertTrue(result["skipped"][0]["reason"].startswith("head-unavailable"))
            result = planner.plan(root, resolve_head=lambda *_: HEAD, read_version=lambda *_: "not-semver")
            self.assertEqual(result["pending"], [])
            self.assertTrue(result["skipped"][0]["reason"].startswith("version-unreadable"))

    def test_plugin_filter_and_unknown_plugin(self) -> None:
        published = {"p": (OLD, ["1.1.0"]), "q": (OLD, ["1.1.0"])}
        result = self.run_plan(published, plugin_id="q")
        self.assertEqual([item["pluginId"] for item in result["pending"]], ["q"])
        with self.assertRaises(planner.PlanError):
            self.run_plan(published, plugin_id="missing")


if __name__ == "__main__":
    unittest.main()
