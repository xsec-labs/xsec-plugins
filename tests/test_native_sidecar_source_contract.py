from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_market  # noqa: E402
import native_sidecars  # noqa: E402
import validate_market  # noqa: E402


SOURCE_REVISION = "b" * 40


def write_native_source(root: Path, recipe: native_sidecars.NativeSidecarRecipe, servers: dict[str, object]) -> Path:
    source = root / recipe.plugin_id
    (source / "com.xsec.desktop" / "frontend").mkdir(parents=True)
    (source / "skills" / recipe.skill_id).mkdir(parents=True)
    manifest = {
        "name": recipe.plugin_id,
        "version": "2.1.0",
        "extensions": {"com.xsec.desktop": {
            "schemaVersion": 2,
            "engines": {"xsec": ">=0.1.0", "pluginApi": "^1.3.0"},
            "entrypoints": {"frontend": "com.xsec.desktop/frontend/index.js"},
            "permissions": {"mcp.servers.register": {}, "native.execute": {}},
        }},
    }
    (source / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    (source / "com.xsec.desktop" / "frontend" / "index.js").write_text("export {};\n", encoding="utf-8")
    (source / "skills" / recipe.skill_id / "SKILL.md").write_text("# Native source\n", encoding="utf-8")
    return source


def sidecar_inputs(root: Path, recipe: native_sidecars.NativeSidecarRecipe) -> dict[tuple[str, str], Path]:
    inputs = {}
    for target in recipe.targets:
        binary = root / target.rust_target
        binary.write_bytes(target.rust_target.encode())
        inputs[(recipe.plugin_id, target.rust_target)] = binary
    return inputs


class NativeSidecarSourceContractTests(unittest.TestCase):
    def test_binary_analysis_source_contains_pinned_license_materials(self) -> None:
        source = ROOT / "plugins" / "com.xsec.binary-analysis"
        required_files = (
            "THIRD_PARTY_NOTICES.md",
            "SBOM.spdx.json",
            "licenses/LGPL-3.0.txt",
            "licenses/GPL-3.0.txt",
            "licenses/Apache-2.0.txt",
            "licenses/Zlib.txt",
            "docs/engine-versions.schema.json",
            "docs/engine-license-inventory.schema.json",
            "scripts/capture_engine_license_inventory.py",
            "scripts/engine_bundle_packaging.py",
            "scripts/package_engine_bundle.py",
            "scripts/source_pin_verification.py",
            "patches/radare2/0001-exclude-gpl-components-in-nogpl-build.patch",
        )
        for relative in required_files:
            with self.subTest(path=relative):
                self.assertTrue((source / relative).is_file(), f"missing {relative}")
        sbom = json.loads((source / "SBOM.spdx.json").read_text(encoding="utf-8"))
        packages = {package["name"]: package for package in sbom["packages"]}
        expected_licenses = {
            "Recurse": "Apache-2.0",
            "radare2": "LGPL-3.0-only",
            "r2ghidra": "LGPL-3.0-only",
            "ghidra-native": "Apache-2.0",
            "zlib": "Zlib",
        }
        for name, license_id in expected_licenses.items():
            with self.subTest(package=name):
                self.assertEqual(packages[name]["licenseDeclared"], license_id)
        self.assertIn(
            native_sidecars.BINARY_ANALYSIS_SOURCE_PATCHSETS["radare2"],
            packages["radare2"]["sourceInfo"],
        )

    def test_registered_sources_follow_their_declared_sidecar_contract(self) -> None:
        for plugin_id, expected_recipe in native_sidecars.RECIPES.items():
            source = ROOT / ".xsec-factory" / "snapshots" / plugin_id
            if not source.is_dir():
                source = ROOT / "plugins" / plugin_id
            if not source.is_dir():
                continue
            recipe = native_sidecars.recipe_for_source(plugin_id, source)
            declared_native = native_sidecars.source_declares_native_sidecar_contract(source, plugin_id)
            with self.subTest(plugin_id=plugin_id), tempfile.TemporaryDirectory(prefix="xsec-source-contract-") as directory:
                output = Path(directory) / plugin_id
                self.assertEqual(recipe is not None, declared_native)
                if recipe is not None:
                    self.assertEqual(recipe, expected_recipe)
                    with self.assertRaisesRegex(ValueError, f"missing native sidecar input: {plugin_id}@"):
                        build_market.build_plugin(source, output, native_sidecar_source_revision=SOURCE_REVISION)
                    continue
                build_market.build_plugin(source, output)
                validate_market.validate_release(plugin_id, output)
                release = json.loads((output / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    {(item["os"], item["arch"]) for item in release["releases"][0]["artifacts"]},
                    {("any", "any")},
                )

    def test_binary_analysis_submodule_declares_its_factory_contract(self) -> None:
        plugin_id = "com.xsec.binary-analysis"
        source = ROOT / "plugins" / plugin_id
        self.assertTrue(source.is_dir())
        self.assertEqual(
            native_sidecars.recipe_for_source(plugin_id, source),
            native_sidecars.BINARY_ANALYSIS_RECIPE,
        )

    def test_native_sidecar_contract_accepts_schema_versions_2_and_3_only(self) -> None:
        permissions = {permission: {} for permission in native_sidecars.NATIVE_SIDECAR_PERMISSIONS}
        for schema_version, expected in ((1, False), (2, True), (3, True), (4, False)):
            manifest = {"extensions": {"com.xsec.desktop": {"schemaVersion": schema_version, "permissions": permissions}}}
            with self.subTest(schema_version=schema_version):
                self.assertIs(native_sidecars.declares_native_sidecar_contract(manifest), expected)

    def test_native_contract_rejects_a_legacy_node_mcp_declaration(self) -> None:
        recipe = native_sidecars.ATTACK_PATH_RECIPE
        servers = {"attack-path": {"type": "stdio", "command": "node", "args": ["sidecar.js"], "cwd": "${PLUGIN_DATA}"}}
        with tempfile.TemporaryDirectory(prefix="xsec-native-contract-") as directory:
            source = write_native_source(Path(directory), recipe, servers)
            with self.assertRaisesRegex(ValueError, "must declare attack-path"):
                native_sidecars.recipe_for_source(recipe.plugin_id, source)

    def test_asset_discovery_native_contract_builds_all_platform_artifacts(self) -> None:
        recipe = native_sidecars.ASSET_DISCOVERY_RECIPE
        servers = {
            "asset-normalize": {"type": "stdio", "command": "./bin/asset-discovery-mcp", "cwd": "${PLUGIN_DATA}"},
            "asset-hunter": {"type": "stdio", "command": "./bin/asset-discovery-mcp", "args": ["--provider", "hunter"], "cwd": "${PLUGIN_DATA}", "env": {"XSEC_ASSET_HUNTER_API_BASE_URL": "https://hunter.qianxin.com/openApi/search"}},
            "asset-fofa": {"type": "stdio", "command": "./bin/asset-discovery-mcp", "args": ["--provider", "fofa"], "cwd": "${PLUGIN_DATA}", "env": {"XSEC_ASSET_FOFA_API_BASE_URL": "https://fofoapi.com"}},
        }
        with tempfile.TemporaryDirectory(prefix="xsec-asset-native-") as directory:
            root = Path(directory)
            source = write_native_source(root, recipe, servers)
            raw = (source / "mcp.json").read_bytes()
            invalid_args = json.loads(raw)
            invalid_args["mcpServers"]["asset-hunter"]["args"] = ["--provider", "fofa"]
            with self.assertRaisesRegex(ValueError, "invalid arguments for asset-hunter"):
                native_sidecars.validate_mcp_declaration(recipe, json.dumps(invalid_args).encode(), "asset mcp.json")
            for server in (
                {"remote-asset": {"type": "streamable-http", "url": "https://example.test/mcp"}},
                {"asset-hunter": {"type": "sse"}},
            ):
                invalid = json.loads(raw)
                invalid["mcpServers"].update(server)
                with self.assertRaisesRegex(ValueError, "must declare only the allowlisted stdio servers"):
                    native_sidecars.validate_mcp_declaration(recipe, json.dumps(invalid).encode(), "asset mcp.json")
            output = root / "output"
            inputs = sidecar_inputs(root, recipe)
            build_market.build_plugin(source, output, native_sidecar_inputs=inputs, native_sidecar_source_revision=SOURCE_REVISION)
            validate_market.validate_release(recipe.plugin_id, output)
            release = json.loads((output / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))
            for artifact, target in zip(release["releases"][0]["artifacts"], recipe.targets, strict=True):
                with zipfile.ZipFile(output / ".xsec-market" / artifact["url"]) as archive:
                    entrypoint = native_sidecars.archive_path_for(recipe, target).as_posix()
                    self.assertEqual(archive.read(entrypoint), inputs[(recipe.plugin_id, target.rust_target)].read_bytes())


if __name__ == "__main__":
    unittest.main()
