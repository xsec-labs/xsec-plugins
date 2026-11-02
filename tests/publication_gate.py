"""Skip gates for checks that need material this checkout does not contain yet.

Before the first protected publication the Factory retains no package
snapshots, and the first-party plugin submodules are not checked out by CI.
Tests that read either are skipped with the reason shown in the run. Each gate
reads the checkout itself, so the tests run again as soon as the material is
present; nothing needs editing at publication time.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / ".xsec-factory" / "snapshots"
PLUGIN_SUBMODULE_ROOT = ROOT / "plugins"
AWAITING_PUBLICATION = "awaiting first protected publication: no package snapshots are retained"


def publication_started() -> bool:
    return SNAPSHOT_ROOT.is_dir() and any(entry.is_dir() for entry in SNAPSHOT_ROOT.iterdir())


def submodule_checked_out(plugin_id: str) -> bool:
    return (PLUGIN_SUBMODULE_ROOT / plugin_id / "plugin.json").is_file()


requires_publication = unittest.skipUnless(publication_started(), AWAITING_PUBLICATION)


def requires_submodule(plugin_id: str):
    return unittest.skipUnless(
        submodule_checked_out(plugin_id),
        f"submodule plugins/{plugin_id} is not checked out",
    )
