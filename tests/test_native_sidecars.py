from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_market  # noqa: E402
import external_source_factory as factory  # noqa: E402
import native_sidecars  # noqa: E402
import validate_market  # noqa: E402


PLUGIN_ID = "com.xsec.attack-path"
PLUGIN_VERSION = "2.0.0"
SIDECAR_PATH = "bin/attack-path-mcp"
SOURCE_REVISION = "a" * 40


def write_attack_path_source(root: Path, command: str = "./bin/attack-path-mcp") -> Path:
    source = root / "source"
    frontend = source / "com.xsec.desktop" / "frontend"
    skill = source / "skills" / "attack-path"
    frontend.mkdir(parents=True)
    skill.mkdir(parents=True)
    manifest = {
        "name": PLUGIN_ID,
        "version": PLUGIN_VERSION,
        "extensions": {
            "com.xsec.desktop": {
                "schemaVersion": 2,
                "engines": {"xsec": ">=0.1.0", "pluginApi": "^1.3.0"},
                "entrypoints": {"frontend": "com.xsec.desktop/frontend/index.js"},
                "permissions": {"mcp.servers.register": {}, "native.execute": {}},
            }
        },
    }
    mcp = {"mcpServers": {"attack-path": {
        "type": "stdio",
        "command": command,
        "cwd": "${PLUGIN_DATA}",
    }}}
    (source / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    (frontend / "index.js").write_text("export {};\n", encoding="utf-8")
    (skill / "SKILL.md").write_text("# Attack path\n", encoding="utf-8")
    return source


def sidecar_inputs(root: Path) -> dict[tuple[str, str], Path]:
    inputs: dict[tuple[str, str], Path] = {}
    for target in native_sidecars.ATTACK_PATH_RECIPE.targets:
        binary = root / target.rust_target
        binary.write_bytes(f"sidecar for {target.rust_target}\n".encode("utf-8"))
        inputs[(PLUGIN_ID, target.rust_target)] = binary
    return inputs


def native_registration() -> factory.Registration:
    return factory.Registration(
        plugin_id=PLUGIN_ID,
        trust_tier="first-party",
        repository="xsec-labs/xsec-plugin-attack-path",
        source_path=PurePosixPath("plugins") / PLUGIN_ID,
        beta_ref="refs/heads/beta",
        stable_ref="refs/heads/main",
        installation="INSTALLED_BY_DEFAULT",
        authentication="ON_INSTALL",
        category="Security",
        status="active",
    )


class NativeSidecarFactoryTests(unittest.TestCase):
    def test_binary_analysis_recipe_requires_verified_engine_bundle(self) -> None:
        recipe = native_sidecars.BINARY_ANALYSIS_RECIPE
        self.assertEqual(len(recipe.targets), 4)
        self.assertEqual(recipe.packed_runtime_kind, "binary-engine")
        self.assertEqual(recipe.max_package_total_bytes, 100 * 1024 * 1024)
        self.assertEqual(recipe.max_package_entries, 4096)
        with self.assertRaisesRegex(ValueError, "missing packed runtime input"):
            native_sidecars.require_packed_runtime_inputs(recipe, {})
        with tempfile.TemporaryDirectory(prefix="xsec-binary-engine-empty-") as directory:
            with self.assertRaisesRegex(ValueError, "engine-versions.json"):
                native_sidecars.binary_engine_manifest(Path(directory), recipe.targets[0])

    def test_binary_analysis_staged_package_enforces_combined_host_quotas(self) -> None:
        recipe = native_sidecars.BINARY_ANALYSIS_RECIPE
        with tempfile.TemporaryDirectory(prefix="xsec-binary-package-quota-") as directory:
            root = Path(directory)
            staged = root / "staged"
            staged.mkdir()
            (staged / "plugin.json").write_bytes(b"{}")
            (staged / "mcp.json").write_bytes(b"{}")
            engine = staged / "engine"
            engine.mkdir()
            (engine / "engine.bin").write_bytes(b"{}")
            byte_limited = replace(
                recipe, max_package_total_bytes=5, max_package_entries=3
            )
            with self.assertRaisesRegex(ValueError, "plugin package is too large"):
                build_market.write_zip(staged, root / "too-large-bytes.zip", byte_limited)

            file_limited = replace(
                recipe, max_package_total_bytes=10, max_package_entries=2
            )
            with self.assertRaisesRegex(ValueError, "exceeds its 2-file limit"):
                build_market.write_zip(staged, root / "too-many-files.zip", file_limited)

    def test_factory_enforces_desktop_downloaded_archive_limit(self) -> None:
        self.assertEqual(build_market.MAX_PACKAGE_ARCHIVE_BYTES, 100 * 1024 * 1024)
        with tempfile.TemporaryDirectory(prefix="xsec-plugin-archive-limit-") as directory:
            artifact = Path(directory) / "oversized.zip"
            artifact.write_bytes(b"x" * 11)
            with self.assertRaisesRegex(ValueError, "archive exceeds 10 bytes"):
                build_market.require_package_archive_size(artifact, maximum_bytes=10)
            self.assertFalse(artifact.exists())

    def test_binary_engine_manifest_rejects_oversized_and_incomplete_contents(self) -> None:
        target = native_sidecars.BINARY_ANALYSIS_RECIPE.targets[0]
        base = {
            "schemaVersion": native_sidecars.BINARY_ENGINE_MANIFEST_SCHEMA_VERSION,
            "platform": "macos-arm64",
            "engineVersions": native_sidecars.BINARY_ANALYSIS_ENGINE_VERSIONS,
            "sourcePins": native_sidecars.BINARY_ANALYSIS_SOURCE_PINS,
            "sourcePatchSets": native_sidecars.BINARY_ANALYSIS_SOURCE_PATCHSETS,
            "licenseInventorySha256": "c" * 64,
        }
        with self.assertRaisesRegex(ValueError, "does not match the artifact platform"):
            native_sidecars.parse_binary_engine_manifest(
                json.dumps({**base, "schemaVersion": True, "files": []}).encode(), target
            )
        wrong_source = {
            **base,
            "sourcePins": {**native_sidecars.BINARY_ANALYSIS_SOURCE_PINS, "zlib": "0" * 40},
            "files": [],
        }
        with self.assertRaisesRegex(ValueError, "source pins"):
            native_sidecars.parse_binary_engine_manifest(json.dumps(wrong_source).encode(), target)
        wrong_inventory = {
            **base,
            "files": [{
                "path": native_sidecars.BINARY_ENGINE_LICENSE_INVENTORY,
                "sha256": "b" * 64,
                "size": 1,
            }],
        }
        with self.assertRaisesRegex(ValueError, "license inventory digest mismatch"):
            native_sidecars.parse_binary_engine_manifest(json.dumps(wrong_inventory).encode(), target)
        too_many = [
            {"path": f"sleigh/{index}.sla", "sha256": "a" * 64, "size": 1}
            for index in range(native_sidecars.MAX_BINARY_ENGINE_FILES + 1)
        ]
        with self.assertRaisesRegex(ValueError, "4,096-file limit"):
            native_sidecars.parse_binary_engine_manifest(
                json.dumps({**base, "files": too_many}).encode(), target
            )
        oversized = [
            {"path": "engine-versions.json", "sha256": "a" * 64, "size": 52_428_801},
            {"path": "sleigh/test.sla", "sha256": "b" * 64, "size": 52_428_801},
        ]
        with self.assertRaisesRegex(ValueError, "100 MiB size limit"):
            native_sidecars.parse_binary_engine_manifest(
                json.dumps({**base, "files": oversized}).encode(), target
            )
        with self.assertRaisesRegex(ValueError, "missing radare2/bin/r2"):
            native_sidecars.require_binary_engine_manifest_components(
                {
                    "engine-versions.json": "a",
                    native_sidecars.BINARY_ENGINE_LICENSE_INVENTORY: "b",
                },
                target,
            )

    def test_binary_engine_manifest_accepts_packaged_r2ghidra_library_names(self) -> None:
        for target in native_sidecars.BINARY_ANALYSIS_RECIPE.targets:
            plugin_name = {
                "macos": "core_ghidra.dylib",
                "linux": "core_ghidra.so",
                "windows": "core_ghidra.dll",
            }[target.os_name]
            paths = {
                "engine-versions.json": "a",
                native_sidecars.BINARY_ENGINE_LICENSE_INVENTORY: "b",
                "radare2/bin/r2.exe" if target.os_name == "windows" else "radare2/bin/r2": "c",
                f"radare2/plugins/{plugin_name}": "d",
                "sleigh/x86.sla": "e",
            }
            with self.subTest(platform=target.os_name, architecture=target.arch):
                native_sidecars.require_binary_engine_manifest_components(paths, target)

    def test_binary_engine_license_inventory_rejects_gpl_and_source_drift(self) -> None:
        inventory = {
            "schemaVersion": 1,
            "radare2Commit": native_sidecars.BINARY_ANALYSIS_SOURCE_PINS["radare2"],
            "components": [
                {"name": name, "license": license_id}
                for name, license_id in native_sidecars.BINARY_ANALYSIS_COMPONENT_LICENSES.items()
            ],
        }
        native_sidecars.validate_binary_engine_license_inventory(inventory)

        inventory["components"].append({"name": "legacy-plugin", "license": "GPL-2.0-or-later"})
        with self.assertRaisesRegex(ValueError, "GPL-licensed component"):
            native_sidecars.validate_binary_engine_license_inventory(inventory)

        inventory["components"].pop()
        inventory["radare2Commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "approved radare2 source"):
            native_sidecars.validate_binary_engine_license_inventory(inventory)

    def test_binary_analysis_release_sbom_contains_validated_runtime_components(self) -> None:
        source_path = ROOT / "plugins" / "com.xsec.binary-analysis" / "SBOM.spdx.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        inventory = {
            "schemaVersion": 1,
            "radare2Commit": native_sidecars.BINARY_ANALYSIS_SOURCE_PINS["radare2"],
            "components": [
                {"name": name, "license": license_id}
                for name, license_id in native_sidecars.BINARY_ANALYSIS_COMPONENT_LICENSES.items()
            ] + [{"name": "plugin/bin/validated-plugin", "license": "MIT"}],
        }
        digest = "d" * 64

        document = native_sidecars.binary_analysis_release_sbom_document(
            source,
            inventory,
            native_sidecars.BINARY_ANALYSIS_RECIPE.targets[0],
            digest,
        )

        packages = {package["name"]: package for package in document["packages"]}
        plugin = packages["com.xsec.binary-analysis"]
        runtime_plugin = packages["plugin/bin/validated-plugin"]
        radare2 = packages["radare2"]
        self.assertEqual(document["name"], "com.xsec.binary-analysis-macos-arm64")
        self.assertTrue(document["documentNamespace"].endswith(digest))
        self.assertEqual(runtime_plugin["licenseDeclared"], "MIT")
        self.assertIn(native_sidecars.BINARY_ANALYSIS_SOURCE_PATCHSETS["radare2"], radare2["sourceInfo"])
        self.assertIn(
            {
                "spdxElementId": plugin["SPDXID"],
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": runtime_plugin["SPDXID"],
            },
            document["relationships"],
        )

    def test_jwt_analysis_sidecar_recipe_matches_plugin_manifest_targets(self) -> None:
        recipe = native_sidecars.JWT_ANALYSIS_RECIPE
        self.assertEqual(recipe.plugin_id, "com.xsec.jwt-analysis")
        self.assertEqual(recipe.source_repository, "xsec-labs/xsec-plugin-jwt-analysis")
        self.assertEqual(len(recipe.targets), 4)
        self.assertEqual(native_sidecars.mcp_command_for(recipe), "./bin/jwt-analysis-mcp")
        self.assertEqual(native_sidecars.mcp_command_for(recipe, recipe.targets[-1]), "./bin/jwt-analysis-mcp.exe")

    def test_browser_runtime_inputs_are_fixed_per_target_and_bound_into_provenance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-browser-runtime-inputs-") as directory:
            root = Path(directory)
            runtime_inputs: dict[tuple[str, str], Path] = {}
            sidecars: dict[str, Path] = {}
            for target in native_sidecars.BROWSER_RECIPE.targets:
                runtime = root / "runtime" / target.rust_target
                node = runtime / native_sidecars.browser_runtime_node_path(target)
                node.parent.mkdir(parents=True)
                node.write_bytes(b"node runtime\n")
                (runtime / "node-version.txt").write_text(
                    native_sidecars.BROWSER_NODE_VERSION + "\n",
                    encoding="ascii",
                )
                for package in ("playwright-core", "cloakbrowser"):
                    package_path = runtime / "node_modules" / package / "package.json"
                    package_path.parent.mkdir(parents=True, exist_ok=True)
                    package_path.write_text('{"name":"' + package + '"}\n', encoding="utf-8")
                for name in native_sidecars.BROWSER_BRIDGE_FILES:
                    bridge = runtime / "bridge" / name
                    bridge.parent.mkdir(parents=True, exist_ok=True)
                    bridge.write_text("export {};\n", encoding="utf-8")
                runtime_inputs[(native_sidecars.BROWSER_RECIPE.plugin_id, target.rust_target)] = runtime
                sidecar = root / "sidecars" / target.rust_target
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                sidecar.write_bytes(b"browser-mcp\n")
                sidecars[target.rust_target] = sidecar

            runtimes = native_sidecars.require_packed_runtime_inputs(
                native_sidecars.BROWSER_RECIPE,
                runtime_inputs,
            )
            provenance = native_sidecars.provenance_for_inputs(
                native_sidecars.BROWSER_RECIPE,
                SOURCE_REVISION,
                sidecars,
                runtimes,
            )
            verified = native_sidecars.validate_provenance(native_sidecars.BROWSER_RECIPE, provenance)
            self.assertEqual(len(verified["targets"]), 4)
            self.assertTrue(all("runtimeManifestSha256" in target for target in verified["targets"]))

    def test_retained_native_beta_reconciliation_reuses_immutable_sidecars(self) -> None:
        """A matching source must not republish a new same-version sidecar build."""

        with tempfile.TemporaryDirectory(prefix="xsec-native-beta-reconciliation-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            factory_root = root / "factory"
            output = factory_root / ".xsec-factory" / "snapshots" / PLUGIN_ID
            original_inputs = sidecar_inputs(root)
            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=original_inputs,
                native_sidecar_source_revision=SOURCE_REVISION,
            )
            release_path = output / ".xsec-market" / "releases.json"
            original_release = json.loads(release_path.read_text(encoding="utf-8"))
            preserved_release_bytes = json.dumps(
                original_release,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            release_path.write_bytes(preserved_release_bytes)
            rebuilt_root = root / "rebuilt"
            rebuilt_root.mkdir()
            rebuilt_inputs = sidecar_inputs(rebuilt_root)
            for binary in rebuilt_inputs.values():
                binary.write_bytes(b"a different Desktop build\n")
            with self.assertRaisesRegex(ValueError, "already contains immutable content"):
                build_market.build_plugin(
                    source,
                    output,
                    native_sidecar_inputs=rebuilt_inputs,
                    native_sidecar_source_revision="b" * 40,
                )
            with self.assertRaisesRegex(ValueError, "retained native Beta sidecars do not match"):
                build_market.build_plugin(
                    source,
                    output,
                    native_sidecar_inputs=rebuilt_inputs,
                    native_sidecar_source_revision="b" * 40,
                    native_sidecar_source_revisions={PLUGIN_ID: SOURCE_REVISION},
                )

            registration = replace(native_registration(), source_path=PurePosixPath("."))
            retained = factory.reconcile_retained_native_beta(
                factory_root,
                source,
                registration,
                root / "retained",
            )
            self.assertEqual(retained["reusable"], "true")
            inputs = {
                (PLUGIN_ID, item["rust_target"]): Path(item["path"])
                for item in json.loads(retained["inputs"])
            }
            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=inputs,
                native_sidecar_source_revision="b" * 40,
                native_sidecar_source_revisions={PLUGIN_ID: SOURCE_REVISION},
            )
            self.assertEqual(
                json.loads(release_path.read_text(encoding="utf-8")),
                original_release,
            )
            self.assertEqual(release_path.read_bytes(), preserved_release_bytes)

    def test_first_party_native_adoption_snapshot_rebuilds_the_selected_beta(self) -> None:
        """Adoption validates native snapshots from retained Sidecar evidence."""

        with tempfile.TemporaryDirectory(prefix="xsec-native-adoption-snapshot-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            factory_root = root / "factory"
            snapshot = factory_root / ".xsec-factory" / "snapshots" / PLUGIN_ID
            snapshot.parent.mkdir(parents=True)
            shutil.copytree(source, snapshot)
            build_market.build_plugin(
                snapshot,
                snapshot,
                native_sidecar_inputs=sidecar_inputs(root),
                native_sidecar_source_revision=SOURCE_REVISION,
            )
            release = json.loads((snapshot / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))
            beta = release["releases"][0]

            factory.validate_disabled_snapshot_artifacts(
                factory_root,
                native_registration(),
                snapshot,
                release,
                beta,
            )

            frontend = snapshot / "com.xsec.desktop" / "frontend" / "index.js"
            frontend.write_text("export const changed = true;\n", encoding="utf-8")
            with self.assertRaisesRegex(factory.ExternalSourceFactoryError, "does not reproduce its immutable Beta artifact"):
                factory.validate_disabled_snapshot_artifacts(
                    factory_root,
                    native_registration(),
                    snapshot,
                    release,
                    beta,
                )

    def test_native_release_evidence_and_main_rebuild_bind_all_retained_sidecars(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-evidence-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            factory_root = root / "factory"
            output = factory_root / ".xsec-factory" / "snapshots" / PLUGIN_ID
            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=sidecar_inputs(root),
                native_sidecar_source_revision=SOURCE_REVISION,
            )
            record = json.loads((output / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))["releases"][0]
            registration = native_registration()
            self.assertEqual(factory.candidate_release_id(factory_root, source, registration, record), record["releaseId"])
            event = factory.publication_event(registration, "beta", SOURCE_REVISION, record, "test-publisher")
            self.assertEqual((event["artifact"]["url"], event["artifact"]["sha256"]), (record["artifacts"][0]["url"], record["artifacts"][0]["sha256"]))

    def test_native_main_rebuild_accepts_portable_and_legacy_beta_records(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-legacy-rebuild-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            factory_root = root / "factory"
            output = factory_root / ".xsec-factory" / "snapshots" / PLUGIN_ID
            build_market.build_plugin(source, output, native_sidecar_inputs=sidecar_inputs(root), native_sidecar_source_revision=SOURCE_REVISION)
            record = json.loads((output / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))["releases"][0]
            legacy = json.loads(json.dumps(record))
            legacy_provenance = legacy["nativeSidecarProvenance"]
            legacy_provenance.pop("targetMatrixVersion")
            legacy_provenance["targets"] = [target for target in legacy_provenance["targets"] if target["os"] != "linux"]
            legacy["artifacts"] = [artifact for artifact in legacy["artifacts"] if artifact["os"] != "linux"]
            legacy["releaseId"] = build_market.release_id(legacy["version"], legacy["engines"], legacy["artifacts"], legacy_provenance)
            self.assertEqual(factory.candidate_release_id(factory_root, source, native_registration(), legacy), legacy["releaseId"])
            with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-portable-") as archive_directory:
                artifact_path = Path(archive_directory) / "portable.xsec-plugin"
                build_market.write_zip(source, artifact_path)
                portable_artifact = {"os": "any", "arch": "any", "url": "artifacts/portable.xsec-plugin", "sha256": build_market.sha256(artifact_path)}
            portable = {"version": record["version"], "engines": record["engines"], "artifacts": [portable_artifact]}
            portable["releaseId"] = build_market.release_id(portable["version"], portable["engines"], portable["artifacts"])
            self.assertEqual(factory.candidate_release_id(factory_root, source, native_registration(), portable), portable["releaseId"])

    def test_builds_and_validates_distinct_artifacts_for_each_supported_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-build-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            output = root / "output" / ".xsec-factory" / "snapshots" / PLUGIN_ID
            inputs = sidecar_inputs(root)

            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=inputs,
                native_sidecar_source_revision=SOURCE_REVISION,
            )

            release = json.loads((output / ".xsec-market" / "releases.json").read_text(encoding="utf-8"))
            artifacts = release["releases"][0]["artifacts"]
            expected = {(target.os_name, target.arch) for target in native_sidecars.ATTACK_PATH_RECIPE.targets}
            self.assertEqual({(artifact["os"], artifact["arch"]) for artifact in artifacts}, expected)
            self.assertNotIn(("any", "any"), {(artifact["os"], artifact["arch"]) for artifact in artifacts})
            provenance = release["releases"][0]["nativeSidecarProvenance"]
            self.assertEqual(provenance["source"]["repository"], "xsec-labs/xSecDesktop")
            self.assertEqual(provenance["source"]["revision"], SOURCE_REVISION)
            self.assertEqual(
                provenance["targetMatrixVersion"],
                native_sidecars.NATIVE_SIDECAR_TARGET_MATRIX_VERSION,
            )
            validate_market.validate_release(PLUGIN_ID, output)

            release_path = output / ".xsec-market" / "releases.json"
            second = release["releases"][0]["artifacts"][1]
            with (output / ".xsec-market" / second["url"]).open("ab") as handle:
                handle.write(b"unexpected archive trailer")
            second["sha256"] = build_market.sha256(output / ".xsec-market" / second["url"])
            release["releases"][0]["releaseId"] = build_market.release_id(
                PLUGIN_VERSION,
                release["releases"][0]["engines"],
                release["releases"][0]["artifacts"],
                provenance,
            )
            release["channels"]["beta"] = {"releaseId": release["releases"][0]["releaseId"]}
            release_path.write_text(json.dumps(release), encoding="utf-8")
            validated = validate_market.validate_release(PLUGIN_ID, output)
            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "not deterministic"):
                validate_market.validate_native_artifact_reproducibility(
                    PLUGIN_ID,
                    source,
                    release["releases"][0]["artifacts"],
                    validated,
                )

            for artifact, target in zip(artifacts, native_sidecars.ATTACK_PATH_RECIPE.targets, strict=True):
                artifact_path = output / ".xsec-market" / artifact["url"]
                with zipfile.ZipFile(artifact_path) as archive:
                    entrypoint = native_sidecars.archive_path_for(native_sidecars.ATTACK_PATH_RECIPE, target).as_posix()
                    self.assertEqual(archive.read(entrypoint), inputs[(PLUGIN_ID, target.rust_target)].read_bytes())
                    mcp = json.loads(archive.read("mcp.json"))
                    self.assertEqual(mcp["mcpServers"]["attack-path"]["command"], f"./{entrypoint}")
            provenance["targets"][0]["sha256"] = "f" * 64
            release["releases"][0]["releaseId"] = build_market.release_id(
                PLUGIN_VERSION,
                release["releases"][0]["engines"],
                artifacts,
                provenance,
            )
            release["channels"]["beta"] = {"releaseId": release["releases"][0]["releaseId"]}
            (output / ".xsec-market" / "releases.json").write_text(json.dumps(release), encoding="utf-8")
            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "digest does not match provenance"):
                validate_market.validate_release(PLUGIN_ID, output)

    def test_historic_three_target_provenance_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-legacy-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            output = root / "output" / ".xsec-factory" / "snapshots" / PLUGIN_ID

            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=sidecar_inputs(root),
                native_sidecar_source_revision=SOURCE_REVISION,
            )

            release_path = output / ".xsec-market" / "releases.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            record = release["releases"][0]
            provenance = record["nativeSidecarProvenance"]
            provenance.pop("targetMatrixVersion")
            provenance["targets"] = [
                target for target in provenance["targets"] if target["os"] != "linux"
            ]
            record["artifacts"] = [
                artifact for artifact in record["artifacts"] if artifact["os"] != "linux"
            ]
            record["releaseId"] = build_market.release_id(
                record["version"],
                record["engines"],
                record["artifacts"],
                provenance,
            )
            release["channels"]["beta"] = {"releaseId": record["releaseId"]}
            release_path.write_text(json.dumps(release), encoding="utf-8")

            validate_market.validate_release(PLUGIN_ID, output)

    def test_build_rejects_a_missing_required_native_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-missing-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            inputs = sidecar_inputs(root)
            missing_target = native_sidecars.ATTACK_PATH_RECIPE.targets[0]
            del inputs[(PLUGIN_ID, missing_target.rust_target)]

            with self.assertRaisesRegex(ValueError, "missing native sidecar input"):
                build_market.build_plugin(
                    source,
                    root / "output",
                    native_sidecar_inputs=inputs,
                    native_sidecar_source_revision=SOURCE_REVISION,
                )

    def test_build_rejects_a_source_sidecar_with_a_windows_extension(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-source-binary-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            source_binary = source / "bin" / "attack-path-mcp.exe"
            source_binary.parent.mkdir()
            source_binary.write_bytes(b"untrusted source binary")

            with self.assertRaisesRegex(ValueError, "must be supplied by the Factory recipe"):
                build_market.build_plugin(
                    source,
                    root / "output",
                    native_sidecar_inputs=sidecar_inputs(root),
                    native_sidecar_source_revision=SOURCE_REVISION,
                )

    def test_release_rejects_platform_artifacts_without_provenance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-release-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            output = root / "output" / ".xsec-factory" / "snapshots" / PLUGIN_ID
            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=sidecar_inputs(root),
                native_sidecar_source_revision=SOURCE_REVISION,
            )
            release_path = output / ".xsec-market" / "releases.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            record = release["releases"][0]
            record.pop("nativeSidecarProvenance")
            record["releaseId"] = build_market.release_id(
                PLUGIN_VERSION,
                record["engines"],
                record["artifacts"],
            )
            release["channels"]["beta"] = {"releaseId": record["releaseId"]}
            release_path.write_text(json.dumps(release), encoding="utf-8")

            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "requires native sidecar provenance"):
                validate_market.validate_release(PLUGIN_ID, output)

    def test_release_rejects_native_provenance_without_native_manifest_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-contract-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            output = root / "output" / ".xsec-factory" / "snapshots" / PLUGIN_ID
            build_market.build_plugin(
                source,
                output,
                native_sidecar_inputs=sidecar_inputs(root),
                native_sidecar_source_revision=SOURCE_REVISION,
            )
            release_path = output / ".xsec-market" / "releases.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            record = release["releases"][0]
            artifact = output / ".xsec-market" / record["artifacts"][0]["url"]
            rewritten = artifact.with_suffix(".rewritten")
            with zipfile.ZipFile(artifact) as original, zipfile.ZipFile(rewritten, "w") as updated:
                for info in original.infolist():
                    content = original.read(info.filename)
                    if info.filename == "plugin.json":
                        manifest = json.loads(content)
                        manifest["extensions"]["com.xsec.desktop"].pop("permissions")
                        content = json.dumps(manifest).encode("utf-8")
                    updated.writestr(info, content)
            rewritten.replace(artifact)
            record["artifacts"][0]["sha256"] = build_market.sha256(artifact)
            record["releaseId"] = build_market.release_id(
                PLUGIN_VERSION,
                record["engines"],
                record["artifacts"],
                record["nativeSidecarProvenance"],
            )
            release["channels"]["beta"] = {"releaseId": record["releaseId"]}
            release_path.write_text(json.dumps(release), encoding="utf-8")

            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "must declare the native sidecar contract"):
                validate_market.validate_release(PLUGIN_ID, output)

    def test_build_rejects_missing_or_invalid_native_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-provenance-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            inputs = sidecar_inputs(root)

            with self.assertRaisesRegex(ValueError, "requires a protected source revision"):
                build_market.build_plugin(source, root / "missing", native_sidecar_inputs=inputs)
            with self.assertRaisesRegex(ValueError, "lowercase 40-character Git SHA"):
                build_market.build_plugin(
                    source,
                    root / "invalid",
                    native_sidecar_inputs=inputs,
                    native_sidecar_source_revision="invalid",
                )

    def test_validation_rejects_any_target_and_invalid_native_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-invalid-") as directory:
            root = Path(directory)
            source = write_attack_path_source(root)
            artifact = root / "any-any.xsec-plugin"
            (source / SIDECAR_PATH).parent.mkdir()
            (source / SIDECAR_PATH).write_bytes(b"sidecar")
            build_market.write_zip(source, artifact)

            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "unsupported target any/any"):
                validate_market.validate_archive(artifact, PLUGIN_ID, PLUGIN_VERSION)

            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "attack-path-mcp.exe"):
                validate_market.validate_archive(
                    artifact,
                    PLUGIN_ID,
                    PLUGIN_VERSION,
                    os_name="windows",
                    arch="x86_64",
                )

            (source / SIDECAR_PATH).unlink()
            build_market.write_zip(source, artifact)
            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "missing bin/attack-path-mcp"):
                validate_market.validate_archive(artifact, PLUGIN_ID, PLUGIN_VERSION, os_name="macos", arch="aarch64")

            invalid = write_attack_path_source(root / "invalid", command="./bin/not-attack-path")
            (invalid / "bin").mkdir()
            (invalid / "bin" / "not-attack-path").write_bytes(b"sidecar")
            build_market.write_zip(invalid, artifact)
            with self.assertRaisesRegex(validate_market.MarketplaceValidationError, "must declare attack-path"):
                validate_market.validate_archive(artifact, PLUGIN_ID, PLUGIN_VERSION, os_name="macos", arch="aarch64")


if __name__ == "__main__":
    unittest.main()
