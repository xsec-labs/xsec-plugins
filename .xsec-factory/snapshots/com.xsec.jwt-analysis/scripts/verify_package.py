from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
REQUIRED_LICENSES = ("LICENSE", "third_party/LICENSE.jwt_tool", "third_party/LICENSE.requests",
                     "third_party/LICENSE.pycryptodomex", "third_party/LICENSE.seclists")


def verify() -> None:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    codex_manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
    sbom = json.loads((ROOT / "third_party/sbom.cdx.json").read_text(encoding="utf-8"))
    if manifest["name"] != "com.xsec.jwt-analysis" or manifest["extensions"]["com.xsec.desktop"]["schemaVersion"] != 2:
        raise ValueError("plugin manifest identity/schema mismatch")
    if (codex_manifest["name"], codex_manifest["version"]) != (manifest["name"], manifest["version"]):
        raise ValueError("Codex plugin manifest identity/version does not match plugin.json")
    if mcp["mcpServers"]["jwt-analysis"]["command"] != "./bin/jwt-analysis-mcp":
        raise ValueError("MCP Sidecar command does not match the Factory recipe")
    if sbom["specVersion"] != "1.6" or sbom["metadata"]["component"]["bom-ref"] != manifest["name"]:
        raise ValueError("CycloneDX SBOM does not describe this plugin")
    _verify_rockyou(sbom)
    _verify_licenses()
    _verify_package_size()


def _verify_rockyou(sbom: dict[str, object]) -> None:
    path = ROOT / "wordlists/rockyou.txt.tar.gz"
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    component = next(item for item in sbom["components"] if item["bom-ref"] == "rockyou")
    if component["hashes"][0]["content"] != digest:
        raise ValueError("RockYou archive hash does not match the SBOM")
    with tarfile.open(path, "r:gz") as archive:
        members = [item for item in archive if item.isfile()]
    if len(members) != 1 or members[0].name != "rockyou.txt":
        raise ValueError("RockYou archive must contain one rockyou.txt file")


def _verify_licenses() -> None:
    missing = [name for name in REQUIRED_LICENSES if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError("required license files are missing: " + ", ".join(missing))


def _verify_package_size() -> None:
    ignored = {".git", ".venv", "build", "dist", ".xsec-build", "__pycache__"}
    files = [path for path in ROOT.rglob("*") if path.is_file() and not ignored.intersection(path.parts)]
    oversized = [path for path in files if path.stat().st_size > MAX_FILE_BYTES]
    total = sum(path.stat().st_size for path in files)
    if oversized or total > MAX_PACKAGE_BYTES:
        raise ValueError("plugin source exceeds the Factory native artifact size limits")


if __name__ == "__main__":
    verify()
    print("JWT plugin package metadata, RockYou, licenses and size checks passed")
