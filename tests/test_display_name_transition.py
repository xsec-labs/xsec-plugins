from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_merged_stable_promotion as verifier  # noqa: E402

REGISTRY = ".xsec-factory/official-registry.json"
MARKET = ".agents/plugins/marketplace.json"
SIDECAR = verifier.MARKETPLACE_SIDECAR


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return done.stdout.decode("utf-8").strip()


def _write(root: Path, path: str, value: object) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _registry(names: dict[str, str], policy: str = "AVAILABLE") -> dict[str, object]:
    rows = []
    for plugin_id in ("com.xsec.p", "com.xsec.q"):
        row: dict[str, object] = {"pluginId": plugin_id, "status": "active", "policy": {"installation": policy}}
        if plugin_id in names:
            row["displayNameEn"] = names[plugin_id]
        rows.append(row)
    return {"schemaVersion": 2, "plugins": rows}


def _market(names: dict[str, str]) -> dict[str, object]:
    rows = []
    for plugin_id in ("com.xsec.p", "com.xsec.q"):
        row: dict[str, object] = {"name": plugin_id, "policy": {"installation": "AVAILABLE"}}
        if plugin_id in names:
            row["displayNameEn"] = names[plugin_id]
        rows.append(row)
    return {"plugins": rows}


class DisplayNameTransitionGitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "--quiet", "--initial-branch=main")
        _git(self.root, "config", "user.name", "Gate Test")
        _git(self.root, "config", "user.email", "gate@example.invalid")
        _write(self.root, REGISTRY, _registry({}))
        _write(self.root, MARKET, _market({}))
        _write(self.root, "scripts/tool.py", "# unchanged\n")
        _git(self.root, "add", "--all")
        _git(self.root, "commit", "--quiet", "-m", "base")
        self.before = _git(self.root, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _commit(self, message: str) -> str:
        _git(self.root, "add", "--all")
        _git(self.root, "commit", "--quiet", "-m", message)
        return _git(self.root, "rev-parse", "HEAD")

    def _transition(self, after: str) -> dict[str, object]:
        return verifier.verify_default_set_transition(self.root, self.before, after)

    def test_name_only_change_without_signed_index_is_display_sync(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        _write(self.root, MARKET, _market({"com.xsec.p": "Asset"}))
        after = self._commit("names")
        self.assertEqual(self._transition(after)["kind"], "display-name-sync")

    def test_registry_only_name_is_pending_and_accepted(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        after = self._commit("registry names")
        self.assertEqual(self._transition(after)["kind"], "display-name-sync")

    def test_name_change_with_a_policy_change_is_refused(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}, policy="INSTALLED_BY_DEFAULT"))
        _write(self.root, MARKET, _market({"com.xsec.p": "Asset"}))
        after = self._commit("names and policy")
        with self.assertRaises(verifier.PromotionVerificationError):
            self._transition(after)

    def test_name_change_plus_another_file_is_refused(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        _write(self.root, "scripts/tool.py", "# edited\n")
        after = self._commit("names and code")
        with self.assertRaises(verifier.PromotionVerificationError):
            self._transition(after)

    def test_index_policy_change_with_a_name_is_refused(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        index = _market({"com.xsec.p": "Asset"})
        index["plugins"][0]["policy"] = {"installation": "INSTALLED_BY_DEFAULT"}
        _write(self.root, MARKET, index)
        after = self._commit("index policy and name")
        with self.assertRaises(verifier.PromotionVerificationError):
            self._transition(after)

    def test_invalid_english_name_is_refused(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": " Padded "}))
        _write(self.root, MARKET, _market({"com.xsec.p": " Padded "}))
        after = self._commit("padded name")
        with self.assertRaises(verifier.PromotionVerificationError):
            self._transition(after)

    def test_index_name_disagreeing_with_registry_is_refused(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        _write(self.root, MARKET, _market({"com.xsec.p": "Other"}))
        after = self._commit("mismatch")
        with self.assertRaises(verifier.PromotionVerificationError):
            self._transition(after)

    def test_signed_index_requires_the_kms_batch_paths(self) -> None:
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        _write(self.root, MARKET, _market({"com.xsec.p": "Asset"}))
        _write(self.root, SIDECAR, {"signed": True})
        after = self._commit("batch")
        with patch.object(verifier, "renewable_sidecars", return_value={SIDECAR}):
            self.assertEqual(self._transition(after)["kind"], "display-name-sync-batch")

    def test_signed_index_without_resigned_sidecar_is_refused(self) -> None:
        _write(self.root, SIDECAR, {"signed": True})
        _git(self.root, "add", "--all")
        _git(self.root, "commit", "--quiet", "-m", "sidecar base")
        self.before = _git(self.root, "rev-parse", "HEAD")
        _write(self.root, REGISTRY, _registry({"com.xsec.p": "Asset"}))
        _write(self.root, MARKET, _market({"com.xsec.p": "Asset"}))
        after = self._commit("unsigned names")
        with patch.object(verifier, "renewable_sidecars", return_value={SIDECAR}):
            with self.assertRaises(verifier.PromotionVerificationError):
                self._transition(after)


if __name__ == "__main__":
    unittest.main()
