from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import external_source_factory as factory  # noqa: E402


def _registry_entry(plugin_id: str = "com.xsec.asset-discovery") -> dict[str, object]:
    registry = json.loads((ROOT / ".xsec-factory" / "official-registry.json").read_text(encoding="utf-8"))
    for entry in registry["plugins"]:
        if entry["pluginId"] == plugin_id:
            return copy.deepcopy(entry)
    raise AssertionError(f"{plugin_id} is not in the registry")


class DisplayNameEnTests(unittest.TestCase):
    def test_registry_carries_english_name_into_marketplace_entry(self) -> None:
        entry = _registry_entry()
        self.assertEqual(entry["displayNameEn"], "Asset discovery")
        registration = factory.parse_registration(entry, 0)
        self.assertEqual(registration.display_name_en, "Asset discovery")
        self.assertEqual(factory.marketplace_entry(registration)["displayNameEn"], "Asset discovery")

    def test_entry_without_english_name_omits_the_key(self) -> None:
        entry = _registry_entry()
        del entry["displayNameEn"]
        registration = factory.parse_registration(entry, 0)
        self.assertEqual(registration.display_name_en, "")
        self.assertNotIn("displayNameEn", factory.marketplace_entry(registration))

    def test_english_name_must_be_a_bounded_string(self) -> None:
        entry = _registry_entry()
        entry["displayNameEn"] = ""
        with self.assertRaises(factory.ExternalSourceFactoryError):
            factory.parse_registration(entry, 0)
        entry["displayNameEn"] = 3
        with self.assertRaises(factory.ExternalSourceFactoryError):
            factory.parse_registration(entry, 0)

    def test_unknown_keys_are_still_rejected(self) -> None:
        entry = _registry_entry()
        entry["displayName"] = "x"
        with self.assertRaises(factory.ExternalSourceFactoryError):
            factory.parse_registration(entry, 0)


if __name__ == "__main__":
    unittest.main()
