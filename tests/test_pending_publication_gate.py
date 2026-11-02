from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_market  # noqa: E402
from validate_market import MarketplaceValidationError  # noqa: E402

EXPECTED_DEFAULTS = {"com.xsec.example"}


def write_index(root: Path, plugins: list[object]) -> None:
    marketplace = root / validate_market.MARKETPLACE_RELATIVE_PATH
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    marketplace.write_text(json.dumps({"name": "xsec-official", "plugins": plugins}), encoding="utf-8")


class PendingPublicationGateTests(unittest.TestCase):
    def test_empty_index_is_accepted_only_when_pending_publication_is_declared(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-pending-publication-") as directory:
            root = Path(directory)
            write_index(root, [])

            with self.assertRaisesRegex(MarketplaceValidationError, "default official plugin set mismatch"):
                validate_market.marketplace_entries(root, EXPECTED_DEFAULTS)
            self.assertEqual(
                validate_market.marketplace_entries(root, EXPECTED_DEFAULTS, pending_publication=True),
                [],
            )

    def test_pending_publication_ends_once_any_snapshot_is_retained(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-pending-publication-") as directory:
            root = Path(directory)
            write_index(root, [])
            (root / validate_market.SNAPSHOT_ROOT_RELATIVE_PATH / "com.xsec.example").mkdir(parents=True)

            with self.assertRaisesRegex(MarketplaceValidationError, "default official plugin set mismatch"):
                validate_market.marketplace_entries(root, EXPECTED_DEFAULTS, pending_publication=True)


if __name__ == "__main__":
    unittest.main()
