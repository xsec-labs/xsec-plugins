from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import external_source_factory as factory  # noqa: E402


def _registry_entry(plugin_id: str = "com.xsec.asset-discovery") -> dict[str, object]:
    # 与官方注册表的行同形；英文名由后续的注册表 PR 写入，这里用夹具。
    return {
        "pluginId": plugin_id,
        "trustTier": "first-party",
        "source": {
            "repository": "xsec-labs/xsec-plugin-asset-discovery",
            "path": ".",
            "refs": {"beta": "refs/heads/beta", "stable": "refs/heads/main"},
        },
        "policy": {"installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_INSTALL"},
        "category": "Security",
        "status": "active",
        "displayNameEn": "Asset discovery",
    }


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
