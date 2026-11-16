from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import maintain_marketplace_defaults as maintenance  # noqa: E402
import verify_merged_stable_promotion as verifier  # noqa: E402


def _registry(**names: str) -> dict[str, object]:
    rows = []
    for plugin_id in ("com.xsec.p", "com.xsec.q"):
        row: dict[str, object] = {"pluginId": plugin_id, "status": "active", "policy": {"installation": "AVAILABLE"}}
        if plugin_id in names:
            row["displayNameEn"] = names[plugin_id]
        rows.append(row)
    return {"schemaVersion": 2, "plugins": rows}


def _marketplace(**names: str) -> dict[str, object]:
    rows = []
    for plugin_id in ("com.xsec.p", "com.xsec.q"):
        row: dict[str, object] = {"name": plugin_id, "policy": {"installation": "AVAILABLE"}}
        if plugin_id in names:
            row["displayNameEn"] = names[plugin_id]
        rows.append(row)
    return {"plugins": rows}


class DisplayNameSyncGateTests(unittest.TestCase):
    def test_index_follows_the_registry_name(self) -> None:
        verifier.check_display_name_changes(
            _registry(**{"com.xsec.p": "Old"}),
            _registry(**{"com.xsec.p": "New"}),
            _marketplace(**{"com.xsec.p": "Old"}),
            _marketplace(**{"com.xsec.p": "New"}),
        )

    def test_registry_only_name_edit_is_pending_until_the_batch_syncs(self) -> None:
        verifier.check_display_name_changes(
            _registry(**{"com.xsec.p": "Old"}),
            _registry(**{"com.xsec.p": "New"}),
            _marketplace(**{"com.xsec.p": "Old"}),
            _marketplace(**{"com.xsec.p": "Old"}),
        )

    def test_index_name_that_disagrees_with_the_registry_is_refused(self) -> None:
        with self.assertRaises(verifier.PromotionVerificationError):
            verifier.check_display_name_changes(
                _registry(**{"com.xsec.p": "New"}),
                _registry(**{"com.xsec.p": "New"}),
                _marketplace(**{"com.xsec.p": "Old"}),
                _marketplace(**{"com.xsec.p": "Other"}),
            )

    def test_index_cannot_drop_a_name_the_registry_still_has(self) -> None:
        with self.assertRaises(verifier.PromotionVerificationError):
            verifier.check_display_name_changes(
                _registry(**{"com.xsec.p": "New"}),
                _registry(**{"com.xsec.p": "New"}),
                _marketplace(**{"com.xsec.p": "Old"}),
                _marketplace(),
            )

    def test_only_the_english_name_is_exempt(self) -> None:
        before = _registry(**{"com.xsec.p": "Old"})
        renamed = copy.deepcopy(before)
        renamed["plugins"][0]["displayNameEn"] = "New"
        self.assertEqual(verifier.without_display_names(before), verifier.without_display_names(renamed))
        changed_status = copy.deepcopy(renamed)
        changed_status["plugins"][0]["status"] = "disabled"
        self.assertNotEqual(verifier.without_display_names(before), verifier.without_display_names(changed_status))

    def test_maintenance_sync_copies_and_drops_names_and_is_idempotent(self) -> None:
        registry = _registry(**{"com.xsec.p": "New"})
        marketplace = _marketplace(**{"com.xsec.p": "Old", "com.xsec.q": "Stale"})
        self.assertTrue(maintenance.sync_display_names(registry, marketplace))
        self.assertEqual(marketplace["plugins"][0]["displayNameEn"], "New")
        self.assertNotIn("displayNameEn", marketplace["plugins"][1])
        self.assertFalse(maintenance.sync_display_names(registry, marketplace))


if __name__ == "__main__":
    unittest.main()
