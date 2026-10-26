"""Static Factory recipes for official native MCP sidecars.

The Factory accepts pre-built binaries only through this module's small,
reviewed allowlist.  It never discovers or executes a command from a plugin
source tree.  A protected release runner is responsible for compiling the
listed Rust targets and passing their regular-file outputs explicitly.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Iterator, Mapping, Sequence


MAX_SIDECAR_BYTES = 64 * 1024 * 1024
MAX_BROWSER_RUNTIME_FILE_BYTES = 256 * 1024 * 1024
MAX_BROWSER_RUNTIME_TOTAL_BYTES = 512 * 1024 * 1024
MAX_BINARY_ENGINE_BYTES = 100 * 1024 * 1024
MAX_BINARY_ENGINE_FILES = 4096
BINARY_ENGINE_MANIFEST_SCHEMA_VERSION = 1
BINARY_ANALYSIS_ENGINE_VERSIONS = {"radare2": "6.2.2", "r2ghidra": "6.2.2"}
BINARY_ANALYSIS_SOURCE_PINS = {
    "radare2": "ad27058877024389292fddf12e1db6e13824ba34",
    "r2ghidra": "1b5cba403c4c8751db8434f6790d5e0f132038f4",
    "ghidra-native": "483ae94bcbc661a77667e52f1eff75928cb6aa2e",
    "zlib": "51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf",
}
BINARY_ANALYSIS_COMPONENT_LICENSES = {
    "radare2": "LGPL-3.0-only",
    "r2ghidra": "LGPL-3.0-only",
    "ghidra-native": "Apache-2.0",
    "zlib": "Zlib",
}
BINARY_ANALYSIS_GHIDRA_NATIVE_PATCHSET_SHA256 = "efde9ac1421a759764737f68a156f7b7aedcffcf81f50d0d7a70542ddd0529b2"
BINARY_ANALYSIS_SOURCE_PATCHSETS = {
    "radare2": "6241d08b3ed5b7bf432d4c3be1ea073b40468737b8a9d486fe4bbfdac7747c2f",
    "ghidra-native": BINARY_ANALYSIS_GHIDRA_NATIVE_PATCHSET_SHA256,
}
BINARY_ENGINE_LICENSE_INVENTORY = "radare2-license-inventory.json"
BROWSER_NODE_VERSION = "v22.23.2"
BROWSER_NODE_DISTRIBUTIONS = {
    "macos-arm64": (
        "node-v22.23.2-darwin-arm64.tar.gz",
        "61130f394c1630d211dd50aecc4353d379480f36d3ac913cd85dbba1aed585c6",
    ),
    "macos-x86_64": (
        "node-v22.23.2-darwin-x64.tar.gz",
        "58e99022c2ff89395576cc7fd4d98cea24bb68081475d5f88b801ee8729fb026",
    ),
    "linux-x86_64": (
        "node-v22.23.2-linux-x64.tar.xz",
        "d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307",
    ),
    "windows-x86_64": (
        "node-v22.23.2-win-x64.zip",
        "1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97",
    ),
}
BROWSER_BRIDGE_FILES = (
    "playwright_bridge.mjs",
    "cloak_launch.mjs",
    "browser_actions.mjs",
    "browser_page_commands.mjs",
    "browser_state_commands.mjs",
    "browser_storage.mjs",
    "browser_evaluate.mjs",
    "browser_console.mjs",
    "browser_transport.mjs",
)
SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NATIVE_SIDECAR_PERMISSIONS = frozenset({"mcp.servers.register", "native.execute"})
NATIVE_SIDECAR_TARGET_MATRIX_VERSION = 2
LEGACY_NATIVE_SIDECAR_RUST_TARGETS = frozenset({
    "aarch64-apple-darwin",
    "x86_64-apple-darwin",
    "x86_64-pc-windows-msvc",
})


@dataclass(frozen=True)
class NativeTarget:
    rust_target: str
    os_name: str
    arch: str


@dataclass(frozen=True)
class NativeStdioServer:
    server_id: str
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    cwd: str = "${PLUGIN_DATA}"


@dataclass(frozen=True)
class NativeSidecarRecipe:
    plugin_id: str
    skill_id: str
    source_repository: str
    archive_path: PurePosixPath
    servers: tuple[NativeStdioServer, ...]
    targets: tuple[NativeTarget, ...]
    max_binary_bytes: int = MAX_SIDECAR_BYTES
    max_package_file_bytes: int = MAX_SIDECAR_BYTES
    max_package_total_bytes: int = 128 * 1024 * 1024
    requires_packed_runtime: bool = False
    packed_runtime_kind: str | None = None
    max_package_entries: int = 10_000


ATTACK_PATH_RECIPE = NativeSidecarRecipe(
    plugin_id="com.xsec.attack-path",
    skill_id="attack-path",
    source_repository="xsec-labs/xSecDesktop",
    archive_path=PurePosixPath("bin/attack-path-mcp"),
    servers=(NativeStdioServer("attack-path"),),
    targets=(
        NativeTarget("aarch64-apple-darwin", "macos", "aarch64"),
        NativeTarget("x86_64-apple-darwin", "macos", "x86_64"),
        NativeTarget("x86_64-unknown-linux-gnu", "linux", "x86_64"),
        NativeTarget("x86_64-pc-windows-msvc", "windows", "x86_64"),
    ),
)

ASSET_DISCOVERY_RECIPE = NativeSidecarRecipe(
    plugin_id="com.xsec.asset-discovery",
    skill_id="asset-discovery",
    source_repository="xsec-labs/xSecDesktop",
    archive_path=PurePosixPath("bin/asset-discovery-mcp"),
    servers=(
        NativeStdioServer("asset-normalize"),
        NativeStdioServer(
            "asset-hunter",
            args=("--provider", "hunter"),
            env=(("XSEC_ASSET_HUNTER_API_BASE_URL", "https://hunter.qianxin.com/openApi/search"),),
        ),
        NativeStdioServer(
            "asset-fofa",
            args=("--provider", "fofa"),
            env=(("XSEC_ASSET_FOFA_API_BASE_URL", "https://fofoapi.com"),),
        ),
    ),
    targets=(
        NativeTarget("aarch64-apple-darwin", "macos", "aarch64"),
        NativeTarget("x86_64-apple-darwin", "macos", "x86_64"),
        NativeTarget("x86_64-unknown-linux-gnu", "linux", "x86_64"),
        NativeTarget("x86_64-pc-windows-msvc", "windows", "x86_64"),
    ),
)

BINARY_ANALYSIS_RECIPE = NativeSidecarRecipe(
    plugin_id="com.xsec.binary-analysis",
    skill_id="binary-analysis",
    source_repository="xsec-labs/xsec-plugin-binary-analysis",
    archive_path=PurePosixPath("bin/binary-analysis-mcp"),
    servers=(NativeStdioServer("binary-analysis"),),
    targets=(
        NativeTarget("aarch64-apple-darwin", "macos", "aarch64"),
        NativeTarget("x86_64-apple-darwin", "macos", "x86_64"),
        NativeTarget("x86_64-unknown-linux-gnu", "linux", "x86_64"),
        NativeTarget("x86_64-pc-windows-msvc", "windows", "x86_64"),
    ),
    max_package_file_bytes=MAX_BINARY_ENGINE_BYTES,
    max_package_total_bytes=MAX_BINARY_ENGINE_BYTES,
    requires_packed_runtime=True,
    packed_runtime_kind="binary-engine",
    max_package_entries=MAX_BINARY_ENGINE_FILES,
)

JWT_ANALYSIS_RECIPE = NativeSidecarRecipe(
    plugin_id="com.xsec.jwt-analysis",
    skill_id="jwt-analysis",
    source_repository="xsec-labs/xsec-plugin-jwt-analysis",
    archive_path=PurePosixPath("bin/jwt-analysis-mcp"),
    servers=(NativeStdioServer("jwt-analysis"),),
    targets=(
        NativeTarget("aarch64-apple-darwin", "macos", "aarch64"),
        NativeTarget("x86_64-apple-darwin", "macos", "x86_64"),
        NativeTarget("x86_64-unknown-linux-gnu", "linux", "x86_64"),
        NativeTarget("x86_64-pc-windows-msvc", "windows", "x86_64"),
    ),
)

BROWSER_RECIPE = NativeSidecarRecipe(
    plugin_id="com.xsec.workspace.browser",
    skill_id="browser-session-lifecycle",
    source_repository="xsec-labs/xSecDesktop",
    archive_path=PurePosixPath("bin/browser-mcp"),
    servers=(NativeStdioServer("browser", cwd="${PLUGIN_ROOT}"),),
    targets=(
        NativeTarget("aarch64-apple-darwin", "macos", "aarch64"),
        NativeTarget("x86_64-apple-darwin", "macos", "x86_64"),
        NativeTarget("x86_64-unknown-linux-gnu", "linux", "x86_64"),
        NativeTarget("x86_64-pc-windows-msvc", "windows", "x86_64"),
    ),
    max_binary_bytes=MAX_BROWSER_RUNTIME_FILE_BYTES,
    max_package_file_bytes=MAX_BROWSER_RUNTIME_FILE_BYTES,
    max_package_total_bytes=512 * 1024 * 1024,
    requires_packed_runtime=True,
    packed_runtime_kind="browser-node",
)

RECIPES = {
    ATTACK_PATH_RECIPE.plugin_id: ATTACK_PATH_RECIPE,
    ASSET_DISCOVERY_RECIPE.plugin_id: ASSET_DISCOVERY_RECIPE,
    BINARY_ANALYSIS_RECIPE.plugin_id: BINARY_ANALYSIS_RECIPE,
    JWT_ANALYSIS_RECIPE.plugin_id: JWT_ANALYSIS_RECIPE,
    BROWSER_RECIPE.plugin_id: BROWSER_RECIPE,
}


def archive_path_for(recipe: NativeSidecarRecipe, target: NativeTarget) -> PurePosixPath:
    """Return the executable pathname for one immutable platform artifact."""

    if target.os_name == "windows":
        return recipe.archive_path.with_suffix(".exe")
    return recipe.archive_path


def mcp_command_for(recipe: NativeSidecarRecipe, target: NativeTarget | None = None) -> str:
    """Return the artifact-local stdio command for source or one platform."""

    path = recipe.archive_path if target is None else archive_path_for(recipe, target)
    return f"./{path.as_posix()}"


def browser_runtime_platform(target: NativeTarget) -> str:
    """Match the platform segment consumed by the browser MCP sidecar."""

    platforms = {
        ("macos", "aarch64"): "macos-arm64",
        ("macos", "x86_64"): "macos-x86_64",
        ("linux", "x86_64"): "linux-x86_64",
        ("windows", "x86_64"): "windows-x86_64",
    }
    try:
        return platforms[(target.os_name, target.arch)]
    except KeyError as error:
        raise ValueError(f"browser runtime has unsupported target {target.os_name}/{target.arch}") from error


def browser_runtime_node_path(target: NativeTarget) -> PurePosixPath:
    filename = "node.exe" if target.os_name == "windows" else "node"
    return PurePosixPath("node") / browser_runtime_platform(target) / filename


def browser_runtime_manifest(root: Path, target: NativeTarget) -> tuple[bytes, dict[str, str]]:
    """Validate one protected runtime tree and return its exact manifest.

    The Factory never copies a runtime out of a plugin source checkout.  The
    protected runner provides a regular-file-only ``runtime`` directory and
    this manifest binds every packed byte to the per-target release metadata.
    """

    require_regular_runtime_root(root)
    files, digests = runtime_file_records(root)
    version_path = root / "node-version.txt"
    if not version_path.is_file() or version_path.read_text(encoding="ascii").strip() != BROWSER_NODE_VERSION:
        raise ValueError(f"packed browser runtime must use Node {BROWSER_NODE_VERSION}")
    require_runtime_components(target, digests)
    document = {
        "schemaVersion": BINARY_ENGINE_MANIFEST_SCHEMA_VERSION,
        "platform": browser_runtime_platform(target),
        "nodeVersion": BROWSER_NODE_VERSION,
        "files": sorted(files, key=lambda item: str(item["path"])),
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n", digests


def packed_runtime_directory(recipe: NativeSidecarRecipe) -> PurePosixPath:
    if recipe.packed_runtime_kind == "binary-engine":
        return PurePosixPath("engine")
    if recipe.packed_runtime_kind == "browser-node":
        return PurePosixPath("runtime")
    raise ValueError(f"native runtime kind is not allowlisted for {recipe.plugin_id}")


def packed_runtime_manifest(
    recipe: NativeSidecarRecipe, root: Path, target: NativeTarget
) -> tuple[bytes, dict[str, str]]:
    if recipe.packed_runtime_kind == "browser-node":
        return browser_runtime_manifest(root, target)
    if recipe.packed_runtime_kind == "binary-engine":
        return binary_engine_manifest(root, target)
    raise ValueError(f"native runtime kind is not allowlisted for {recipe.plugin_id}")


def binary_engine_manifest(root: Path, target: NativeTarget) -> tuple[bytes, dict[str, str]]:
    require_regular_runtime_root(root)
    files, digests = runtime_file_records(
        root, MAX_BINARY_ENGINE_BYTES, MAX_BINARY_ENGINE_BYTES, MAX_BINARY_ENGINE_FILES
    )
    require_binary_engine_components(root, target, digests)
    document = {
        "schemaVersion": 1,
        "platform": browser_runtime_platform(target),
        "engineVersions": BINARY_ANALYSIS_ENGINE_VERSIONS,
        "sourcePins": BINARY_ANALYSIS_SOURCE_PINS,
        "sourcePatchSets": BINARY_ANALYSIS_SOURCE_PATCHSETS,
        "licenseInventorySha256": digests[BINARY_ENGINE_LICENSE_INVENTORY],
        "files": sorted(files, key=lambda item: str(item["path"])),
    }
    manifest = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    return manifest, digests


def require_binary_engine_components(
    root: Path, target: NativeTarget, digests: Mapping[str, str]
) -> None:
    versions_path = root / "engine-versions.json"
    try:
        versions = json.loads(versions_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"binary engine bundle has no valid engine-versions.json: {error}") from error
    expected_versions = binary_engine_versions_document()
    if (
        not isinstance(versions, dict)
        or type(versions.get("schemaVersion")) is not int
        or set(versions) != set(expected_versions) | {"licenseInventorySha256"}
        or {key: value for key, value in versions.items() if key != "licenseInventorySha256"}
        != expected_versions
        or not isinstance(versions.get("licenseInventorySha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", versions["licenseInventorySha256"])
    ):
        raise ValueError("binary engine bundle metadata does not match the approved source baseline")
    inventory_digest = versions["licenseInventorySha256"]
    if digests.get(BINARY_ENGINE_LICENSE_INVENTORY) != inventory_digest:
        raise ValueError("binary engine license inventory digest does not match engine-versions.json")
    inventory_path = root / BINARY_ENGINE_LICENSE_INVENTORY
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"binary engine license inventory is invalid: {error}") from error
    validate_binary_engine_license_inventory(inventory)
    require_binary_engine_manifest_components(digests, target)


def binary_engine_versions_document() -> dict[str, object]:
    return {
        "schemaVersion": BINARY_ENGINE_MANIFEST_SCHEMA_VERSION,
        "radare2": {
            "version": BINARY_ANALYSIS_ENGINE_VERSIONS["radare2"],
            "commit": BINARY_ANALYSIS_SOURCE_PINS["radare2"],
            "license": BINARY_ANALYSIS_COMPONENT_LICENSES["radare2"],
        },
        "r2ghidra": {
            "version": BINARY_ANALYSIS_ENGINE_VERSIONS["r2ghidra"],
            "commit": BINARY_ANALYSIS_SOURCE_PINS["r2ghidra"],
            "license": BINARY_ANALYSIS_COMPONENT_LICENSES["r2ghidra"],
        },
        "dependencies": {
            name: {
                "commit": BINARY_ANALYSIS_SOURCE_PINS[name],
                "license": license,
            }
            for name, license in BINARY_ANALYSIS_COMPONENT_LICENSES.items()
            if name in {"ghidra-native", "zlib"}
        },
        "ghidraNativePatchSetSha256": BINARY_ANALYSIS_GHIDRA_NATIVE_PATCHSET_SHA256,
        "radare2PatchSetSha256": BINARY_ANALYSIS_SOURCE_PATCHSETS["radare2"],
        "requiredRadare2ConfigureFlags": ["--without-gpl"],
        "licenseInventoryPath": BINARY_ENGINE_LICENSE_INVENTORY,
    }


def validate_binary_engine_license_inventory(document: object) -> None:
    expected_keys = {"schemaVersion", "radare2Commit", "components"}
    if (
        not isinstance(document, dict)
        or set(document) != expected_keys
        or type(document.get("schemaVersion")) is not int
        or document.get("schemaVersion") != BINARY_ENGINE_MANIFEST_SCHEMA_VERSION
        or document.get("radare2Commit") != BINARY_ANALYSIS_SOURCE_PINS["radare2"]
    ):
        raise ValueError("binary engine license inventory does not match the approved radare2 source")
    components = document.get("components")
    if not isinstance(components, list) or len(components) < len(BINARY_ANALYSIS_COMPONENT_LICENSES):
        raise ValueError("binary engine license inventory is incomplete")
    seen: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict) or set(component) != {"name", "license"}:
            raise ValueError("binary engine license inventory contains an invalid component")
        name, license_id = component.get("name"), component.get("license")
        if (
            not isinstance(name, str) or not name.strip()
            or not isinstance(license_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", license_id)
        ):
            raise ValueError("binary engine license inventory contains an invalid component")
        key = name.casefold()
        if key in seen:
            raise ValueError("binary engine license inventory contains duplicate components")
        if license_id.upper().startswith("GPL"):
            raise ValueError(f"binary engine includes GPL-licensed component: {name}")
        seen[key] = license_id
    for name, license_id in BINARY_ANALYSIS_COMPONENT_LICENSES.items():
        if seen.get(name.casefold()) != license_id:
            raise ValueError(f"binary engine license inventory is missing approved component: {name}")


def binary_engine_spdx_package_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9.-]+", "-", name).strip("-")[:48] or "component"
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return f"SPDXRef-Package-{slug}-{suffix}"


def binary_engine_spdx_package(name: str, license_id: str) -> dict[str, object]:
    package: dict[str, object] = {
        "SPDXID": binary_engine_spdx_package_id(name),
        "name": name,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": license_id,
        "licenseDeclared": license_id,
        "licenseComments": "License reported by the target-specific radare2 -Vj inventory.",
    }
    if name in {"radare2", "r2ghidra"}:
        package["versionInfo"] = BINARY_ANALYSIS_ENGINE_VERSIONS[name]
    if name == "radare2":
        package["sourceInfo"] = (
            f"Pinned source commit {BINARY_ANALYSIS_SOURCE_PINS[name]}; "
            f"patch set SHA-256 {BINARY_ANALYSIS_SOURCE_PATCHSETS['radare2']}"
        )
    elif name in BINARY_ANALYSIS_SOURCE_PINS:
        package["sourceInfo"] = f"Pinned source commit {BINARY_ANALYSIS_SOURCE_PINS[name]}"
    return package


def add_engine_sbom_packages(
    packages: list[object], inventory: Mapping[str, object]
) -> tuple[list[object], dict[str, dict[str, object]]]:
    by_name = {
        item["name"]: item
        for item in packages
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if len(by_name) != len(packages):
        raise ValueError("binary-analysis source SBOM contains invalid or duplicate packages")
    for component in inventory["components"]:
        name, license_id = component["name"], component["license"]
        package = by_name.get(name)
        if package is None:
            package = binary_engine_spdx_package(name, license_id)
            packages.append(package)
            by_name[name] = package
        else:
            package["licenseConcluded"] = license_id
            package["licenseDeclared"] = license_id
    return packages, by_name


def binary_analysis_sbom_relationships(
    source: Mapping[str, object], packages: Mapping[str, dict[str, object]], plugin_id: str
) -> list[dict[str, str]]:
    relationships = source.get("relationships", [])
    if not isinstance(relationships, list):
        raise ValueError("binary-analysis source SBOM relationships are invalid")
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    for relation in relationships:
        if not isinstance(relation, dict):
            raise ValueError("binary-analysis source SBOM relationship is invalid")
        if relation.get("spdxElementId") != plugin_id:
            key = (
                str(relation.get("spdxElementId")),
                str(relation.get("relationshipType")),
                str(relation.get("relatedSpdxElement")),
            )
            result[key] = relation
    for name, package in packages.items():
        if name != "com.xsec.binary-analysis":
            key = (plugin_id, "DEPENDS_ON", str(package["SPDXID"]))
            result[key] = dict(zip(("spdxElementId", "relationshipType", "relatedSpdxElement"), key))
    for name in ("ghidra-native", "zlib"):
        if "r2ghidra" in packages and name in packages:
            key = (str(packages["r2ghidra"]["SPDXID"]), "DEPENDS_ON", str(packages[name]["SPDXID"]))
            result[key] = dict(zip(("spdxElementId", "relationshipType", "relatedSpdxElement"), key))
    describes = ("SPDXRef-DOCUMENT", "DESCRIBES", plugin_id)
    result[describes] = dict(zip(("spdxElementId", "relationshipType", "relatedSpdxElement"), describes))
    return [result[key] for key in sorted(result)]


def binary_analysis_release_sbom_document(
    source: object, inventory: object, target: NativeTarget, inventory_digest: str
) -> dict[str, object]:
    if not isinstance(source, dict) or not isinstance(source.get("packages"), list):
        raise ValueError("binary-analysis source SBOM is invalid")
    if not isinstance(source.get("documentNamespace"), str):
        raise ValueError("binary-analysis source SBOM has no document namespace")
    validate_binary_engine_license_inventory(inventory)
    packages, by_name = add_engine_sbom_packages(list(source["packages"]), inventory)
    plugin = by_name.get("com.xsec.binary-analysis")
    if plugin is None or not isinstance(plugin.get("SPDXID"), str):
        raise ValueError("binary-analysis source SBOM has no plugin package")
    document = dict(source)
    platform = browser_runtime_platform(target)
    document["name"] = f"com.xsec.binary-analysis-{platform}"
    document["documentNamespace"] = f"{source['documentNamespace']}/{platform}/{inventory_digest}"
    document["packages"] = sorted(packages, key=lambda item: str(item.get("name", "")))
    document["relationships"] = binary_analysis_sbom_relationships(source, by_name, plugin["SPDXID"])
    return document


def write_binary_analysis_release_sbom(
    staging: Path, runtime_root: Path, target: NativeTarget
) -> None:
    sbom_path = staging / "SBOM.spdx.json"
    inventory_path = runtime_root / BINARY_ENGINE_LICENSE_INVENTORY
    try:
        source = json.loads(sbom_path.read_text(encoding="utf-8"))
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"read binary-analysis SBOM input: {error}") from error
    digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    document = binary_analysis_release_sbom_document(source, inventory, target, digest)
    sbom_path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def require_binary_engine_manifest_components(
    files: Mapping[str, object], target: NativeTarget
) -> None:
    paths = set(files)
    if "engine-versions.json" not in paths:
        raise ValueError("binary engine bundle is missing engine-versions.json")
    if BINARY_ENGINE_LICENSE_INVENTORY not in paths:
        raise ValueError(f"binary engine bundle is missing {BINARY_ENGINE_LICENSE_INVENTORY}")
    executable = "radare2/bin/r2.exe" if target.os_name == "windows" else "radare2/bin/r2"
    if executable not in paths:
        raise ValueError(f"binary engine bundle is missing {executable}")
    plugin_names = {
        "macos": "core_ghidra.dylib",
        "linux": "core_ghidra.so",
        "windows": "core_ghidra.dll",
    }
    plugin_path = (PurePosixPath("radare2/plugins") / plugin_names[target.os_name]).as_posix()
    if plugin_path not in paths:
        raise ValueError(f"binary engine bundle is missing {plugin_path}")
    if not any(path.startswith("sleigh/") for path in paths):
        raise ValueError("binary engine bundle is missing SLEIGH data")


def require_regular_runtime_root(root: Path) -> None:
    try:
        metadata = os.lstat(root)
    except OSError as error:
        raise ValueError(f"read packed browser runtime {root}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("packed browser runtime must be a regular directory")


def runtime_file_records(
    root: Path,
    max_file_bytes: int = MAX_BROWSER_RUNTIME_FILE_BYTES,
    max_total_bytes: int = MAX_BROWSER_RUNTIME_TOTAL_BYTES,
    max_entries: int | None = None,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    files: list[dict[str, object]] = []
    digests: dict[str, str] = {}
    total_bytes = 0
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories:
            candidate = current_path / name
            metadata = os.lstat(candidate)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"packed browser runtime must contain regular directories: {candidate}")
        for name in names:
            candidate = current_path / name
            metadata = os.lstat(candidate)
            relative = PurePosixPath(candidate.relative_to(root).as_posix())
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise ValueError(f"packed browser runtime must contain regular files: {candidate}")
            if metadata.st_size == 0 or metadata.st_size > max_file_bytes:
                raise ValueError(f"packed browser runtime file is outside the size budget: {relative}")
            total_bytes += metadata.st_size
            if total_bytes > max_total_bytes:
                raise ValueError("packed browser runtime exceeds the total size budget")
            if max_entries is not None and len(files) >= max_entries:
                raise ValueError(f"packed runtime exceeds the {max_entries}-file limit")
            key = relative.as_posix()
            if key == "manifest.json":
                raise ValueError("packed browser runtime must not supply its own manifest.json")
            digest = sha256_file(candidate)
            digests[key] = digest
            files.append({"path": key, "sha256": digest, "size": metadata.st_size})
    return files, digests


def require_runtime_components(target: NativeTarget, digests: Mapping[str, str]) -> None:
    node = browser_runtime_node_path(target).as_posix()
    required = {
        node,
        "node-version.txt",
        "node_modules/playwright-core/package.json",
        "node_modules/cloakbrowser/package.json",
        *(f"bridge/{name}" for name in BROWSER_BRIDGE_FILES),
    }
    if not required.issubset(digests):
        missing = sorted(required - set(digests))[0]
        raise ValueError(f"packed browser runtime is missing {missing}")


@dataclass(frozen=True)
class PackedRuntimeInput:
    root: Path
    manifest: bytes
    manifest_sha256: str


def require_packed_runtime_inputs(
    recipe: NativeSidecarRecipe,
    inputs: Mapping[tuple[str, str], Path],
) -> dict[str, PackedRuntimeInput]:
    """Require a protected per-target runtime only for recipes that need one."""

    supplied = {identity for identity in inputs if identity[0] == recipe.plugin_id}
    if not recipe.requires_packed_runtime:
        if supplied:
            raise ValueError(f"native runtime input is not allowed for {recipe.plugin_id}")
        return {}
    expected = {(recipe.plugin_id, target.rust_target) for target in recipe.targets}
    unknown = supplied - expected
    if unknown:
        plugin_id, target = sorted(unknown)[0]
        raise ValueError(f"native runtime input is not allowlisted: {plugin_id}@{target}")
    missing = expected - supplied
    if missing:
        plugin_id, target = sorted(missing)[0]
        raise ValueError(f"missing packed runtime input: {plugin_id}@{target}")
    result: dict[str, PackedRuntimeInput] = {}
    for target in recipe.targets:
        root = inputs[(recipe.plugin_id, target.rust_target)]
        manifest, _ = packed_runtime_manifest(recipe, root, target)
        result[target.rust_target] = PackedRuntimeInput(
            root=root.resolve(strict=True),
            manifest=manifest,
            manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        )
    return result


def provenance_for_inputs(
    recipe: NativeSidecarRecipe,
    source_revision: str,
    inputs: Mapping[str, Path],
    runtime_inputs: Mapping[str, PackedRuntimeInput] | None = None,
) -> dict[str, object]:
    """Return immutable source and binary evidence for one native release."""

    if not SOURCE_REVISION_PATTERN.fullmatch(source_revision):
        raise ValueError("native sidecar source revision must be a lowercase 40-character Git SHA")
    runtimes = runtime_inputs or {}
    targets = []
    for target in recipe.targets:
        binary = inputs.get(target.rust_target)
        if binary is None:
            raise ValueError(f"missing native sidecar input: {recipe.plugin_id}@{target.rust_target}")
        record: dict[str, object] = {
            "rustTarget": target.rust_target,
            "os": target.os_name,
            "arch": target.arch,
            "sha256": sha256_file(binary),
        }
        if recipe.requires_packed_runtime:
            runtime = runtimes.get(target.rust_target)
            if runtime is None:
                raise ValueError(f"missing packed runtime input: {recipe.plugin_id}@{target.rust_target}")
            record["runtimeManifestSha256"] = runtime.manifest_sha256
        targets.append(record)
    return {
        "source": {
            "repository": recipe.source_repository,
            "revision": source_revision,
        },
        "targetMatrixVersion": NATIVE_SIDECAR_TARGET_MATRIX_VERSION,
        "targets": targets,
    }


def validate_provenance(recipe: NativeSidecarRecipe, value: object) -> dict[str, object]:
    """Validate signed release metadata before comparing packaged binaries."""

    if not isinstance(value, dict) or set(value) not in (
        {"source", "targets"},
        {"source", "targetMatrixVersion", "targets"},
    ):
        raise ValueError("native sidecar provenance has an unsupported schema")
    targets = value.get("targets")
    revision = provenance_source_revision(recipe, value.get("source"))
    target_matrix_version = value.get("targetMatrixVersion")
    expected_targets = targets_for_provenance_version(recipe, target_matrix_version)
    if not isinstance(targets, list) or len(targets) != len(expected_targets):
        raise ValueError("native sidecar provenance must declare every allowlisted target exactly once")
    actual: dict[str, dict[str, object]] = {}
    for target in targets:
        expected_fields = {"rustTarget", "os", "arch", "sha256"}
        if recipe.requires_packed_runtime:
            expected_fields.add("runtimeManifestSha256")
        if not isinstance(target, dict) or set(target) != expected_fields:
            raise ValueError("native sidecar provenance target has an invalid schema")
        rust_target = target.get("rustTarget")
        digest = target.get("sha256")
        if not isinstance(rust_target, str) or rust_target in actual:
            raise ValueError("native sidecar provenance has duplicate or invalid Rust targets")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("native sidecar provenance target must have a lowercase SHA-256")
        runtime_digest = target.get("runtimeManifestSha256")
        if recipe.requires_packed_runtime and (
            not isinstance(runtime_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", runtime_digest)
        ):
            raise ValueError("packed runtime manifest must have a lowercase SHA-256")
        actual[rust_target] = target
    normalized_targets = []
    for expected in expected_targets:
        target = actual.get(expected.rust_target)
        if target is None or target.get("os") != expected.os_name or target.get("arch") != expected.arch:
            raise ValueError(f"native sidecar provenance has invalid target {expected.rust_target}")
        normalized_target: dict[str, object] = {
            "rustTarget": expected.rust_target,
            "os": expected.os_name,
            "arch": expected.arch,
            "sha256": target["sha256"],
        }
        if recipe.requires_packed_runtime:
            normalized_target["runtimeManifestSha256"] = target["runtimeManifestSha256"]
        normalized_targets.append(normalized_target)
    normalized = {
        "source": {"repository": recipe.source_repository, "revision": revision},
        "targets": normalized_targets,
    }
    if target_matrix_version is not None:
        normalized["targetMatrixVersion"] = target_matrix_version
    return normalized


def provenance_source_revision(recipe: NativeSidecarRecipe, source: object) -> str:
    """Validate the immutable source evidence and return its revision."""

    if not isinstance(source, dict) or set(source) != {"repository", "revision"}:
        raise ValueError("native sidecar provenance source must contain repository and revision")
    if source.get("repository") != recipe.source_repository:
        raise ValueError(f"native sidecar provenance source must be {recipe.source_repository}")
    revision = source.get("revision")
    if not isinstance(revision, str) or not SOURCE_REVISION_PATTERN.fullmatch(revision):
        raise ValueError("native sidecar provenance source revision must be a lowercase 40-character Git SHA")
    return revision


def targets_for_provenance_version(
    recipe: NativeSidecarRecipe,
    target_matrix_version: object,
) -> tuple[NativeTarget, ...]:
    """Return the exact target matrix selected by signed provenance."""

    if target_matrix_version is None:
        return tuple(
            target
            for target in recipe.targets
            if target.rust_target in LEGACY_NATIVE_SIDECAR_RUST_TARGETS
        )
    if target_matrix_version == NATIVE_SIDECAR_TARGET_MATRIX_VERSION:
        return recipe.targets
    raise ValueError("native sidecar provenance has an unsupported target matrix version")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_native_sidecar_inputs(values: Sequence[str]) -> dict[tuple[str, str], Path]:
    """Parse ``plugin-id@rust-target=path`` inputs without shell expansion."""

    parsed: dict[tuple[str, str], Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        plugin_id, at, rust_target = key.partition("@")
        if not separator or not at or not plugin_id or not rust_target or not raw_path:
            raise ValueError("native sidecar input must use plugin-id@rust-target=path")
        identity = (plugin_id, rust_target)
        if identity in parsed:
            raise ValueError(f"duplicate native sidecar input for {plugin_id}@{rust_target}")
        recipe = RECIPES.get(plugin_id)
        if recipe is None:
            raise ValueError(f"native sidecar input is not allowlisted: {plugin_id}@{rust_target}")
        target_for(recipe, rust_target)
        parsed[identity] = Path(raw_path)
    return parsed


def parse_packed_runtime_inputs(values: Sequence[str]) -> dict[tuple[str, str], Path]:
    """Parse protected ``plugin-id@rust-target=runtime-directory`` inputs."""

    parsed: dict[tuple[str, str], Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        plugin_id, at, rust_target = key.partition("@")
        if not separator or not at or not plugin_id or not rust_target or not raw_path:
            raise ValueError("packed runtime input must use plugin-id@rust-target=directory")
        identity = (plugin_id, rust_target)
        if identity in parsed:
            raise ValueError(f"duplicate packed runtime input for {plugin_id}@{rust_target}")
        recipe = RECIPES.get(plugin_id)
        if recipe is None or not recipe.requires_packed_runtime:
            raise ValueError(f"packed runtime input is not allowlisted: {plugin_id}@{rust_target}")
        target_for(recipe, rust_target)
        parsed[identity] = Path(raw_path)
    return parsed


def parse_native_sidecar_source_revisions(values: Sequence[str]) -> dict[str, str]:
    """Parse allowlisted ``plugin-id=source-revision`` provenance overrides."""

    parsed: dict[str, str] = {}
    for value in values:
        plugin_id, separator, revision = value.partition("=")
        if not separator or not plugin_id or not SOURCE_REVISION_PATTERN.fullmatch(revision):
            raise ValueError("native sidecar source revision must use plugin-id=lowercase-40-character-Git-SHA")
        if plugin_id in parsed:
            raise ValueError(f"duplicate native sidecar source revision for {plugin_id}")
        if plugin_id not in RECIPES:
            raise ValueError(f"native sidecar source revision is not allowlisted: {plugin_id}")
        parsed[plugin_id] = revision
    return parsed


def recipe_for_source(plugin_id: str, source_dir: Path) -> NativeSidecarRecipe | None:
    """Return the recipe only for an explicit native Agent Plugin contract."""

    if not source_declares_native_sidecar_contract(source_dir, plugin_id):
        return None
    recipe = RECIPES.get(plugin_id)
    if recipe is None:
        raise ValueError(f"native MCP plugin is not on the Factory allowlist: {plugin_id}")
    mcp_path = source_dir / "mcp.json"
    if not os.path.lexists(mcp_path):
        raise ValueError(f"native MCP plugin must provide mcp.json: {plugin_id}")
    raw = read_regular_mcp(mcp_path, f"{plugin_id} mcp.json")
    validate_mcp_declaration(recipe, raw, f"{plugin_id} mcp.json")
    return recipe


def source_declares_native_sidecar_contract(source_dir: Path, plugin_id: str) -> bool:
    """Read the manifest marker that opts a source into Factory sidecars."""

    path = source_dir / "plugin.json"
    raw = read_regular_mcp(path, f"{plugin_id} plugin.json")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{plugin_id} plugin.json is invalid JSON: {error}") from error
    return declares_native_sidecar_contract(manifest)


def declares_native_sidecar_contract(manifest: object) -> bool:
    """Require the v2 or v3 host schema and its explicit native authorities."""

    if not isinstance(manifest, dict):
        return False
    extensions = manifest.get("extensions")
    desktop = extensions.get("com.xsec.desktop") if isinstance(extensions, dict) else None
    permissions = desktop.get("permissions") if isinstance(desktop, dict) else None
    return (
        isinstance(desktop, dict)
        and desktop.get("schemaVersion") in (2, 3)
        and isinstance(permissions, dict)
        and NATIVE_SIDECAR_PERMISSIONS.issubset(permissions)
    )


def read_regular_mcp(path: Path, label: str) -> bytes:
    """Read mcp.json only after refusing symlinks and non-file entries."""

    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ValueError(f"read {label}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError(f"read {label}: {error}") from error


def mcp_servers(raw: bytes, label: str) -> Mapping[str, object]:
    """Parse the portable MCP document before applying a native policy."""

    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON: {error}") from error
    servers = value.get("mcpServers") if isinstance(value, dict) else None
    if not isinstance(servers, dict):
        raise ValueError(f"{label} must contain an mcpServers object")
    return servers


def declares_stdio_server(raw: bytes, label: str) -> bool:
    return any(isinstance(server, dict) and server.get("type") == "stdio" for server in mcp_servers(raw, label).values())


def validate_mcp_declaration(
    recipe: NativeSidecarRecipe,
    raw: bytes,
    label: str,
    target: NativeTarget | None = None,
) -> None:
    servers = mcp_servers(raw, label)
    expected_names = {server.server_id for server in recipe.servers}
    if set(servers.keys()) != expected_names:
        raise ValueError(f"{label} must declare only the allowlisted stdio servers")
    for server in servers.values():
        if not isinstance(server, dict) or server.get("type") != "stdio":
            raise ValueError(f"{label} must declare only the allowlisted stdio servers")
    command = mcp_command_for(recipe, target)
    for expected in recipe.servers:
        server = servers.get(expected.server_id)
        if not isinstance(server, dict) or server.get("command") != command:
            raise ValueError(f"{label} must declare {expected.server_id} at {command}")
        if server.get("args", []) != list(expected.args):
            raise ValueError(f"{label} has invalid arguments for {expected.server_id}")
        if server.get("cwd") != expected.cwd:
            raise ValueError(f"{label} must run {expected.server_id} with cwd={expected.cwd}")
        if server.get("env", {}) != dict(expected.env):
            raise ValueError(f"{label} has invalid environment for {expected.server_id}")


def require_inputs(recipe: NativeSidecarRecipe, inputs: Mapping[tuple[str, str], Path]) -> dict[str, Path]:
    expected = {(recipe.plugin_id, target.rust_target) for target in recipe.targets}
    supplied = {identity for identity in inputs if identity[0] == recipe.plugin_id}
    unknown = supplied - expected
    if unknown:
        plugin_id, target = sorted(unknown)[0]
        raise ValueError(f"native sidecar input is not allowlisted: {plugin_id}@{target}")
    missing = expected - supplied
    if missing:
        plugin_id, target = sorted(missing)[0]
        raise ValueError(f"missing native sidecar input: {plugin_id}@{target}")
    return {
        target: require_regular_input(inputs[(recipe.plugin_id, target)], recipe.max_binary_bytes)
        for _, target in expected
    }


def require_regular_input(path: Path, max_bytes: int = MAX_SIDECAR_BYTES) -> Path:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ValueError(f"read native sidecar input {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size == 0 or metadata.st_size > max_bytes:
        raise ValueError(f"native sidecar input must be a non-empty regular file within {max_bytes} bytes: {path}")
    return path.resolve(strict=True)


@contextmanager
def staged_plugin(
    source_dir: Path,
    files: Sequence[Path],
    recipe: NativeSidecarRecipe,
    target: NativeTarget,
    sidecar: Path,
    packed_runtime: PackedRuntimeInput | None = None,
) -> Iterator[Path]:
    """Copy verified source files and one allowlisted binary into a clean tree."""

    with tempfile.TemporaryDirectory(prefix="xsec-native-sidecar-") as directory:
        staging = Path(directory) / "plugin"
        copy_source_files(
            source_dir,
            staging,
            files,
            native_archive_paths(recipe),
            packed_runtime_directory(recipe).as_posix() if recipe.requires_packed_runtime else None,
        )
        rewrite_mcp_command(staging, recipe, target)
        entrypoint = staging / archive_path_for(recipe, target)
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sidecar, entrypoint)
        entrypoint.chmod(0o755)
        if recipe.requires_packed_runtime:
            if packed_runtime is None:
                raise ValueError(f"packed runtime is required for {recipe.plugin_id}")
            install_packed_runtime(staging, recipe, target, packed_runtime)
            if recipe.packed_runtime_kind == "binary-engine":
                write_binary_analysis_release_sbom(staging, packed_runtime.root, target)
        yield staging


def native_archive_paths(recipe: NativeSidecarRecipe) -> set[PurePosixPath]:
    return {archive_path_for(recipe, target) for target in recipe.targets}


def copy_source_files(
    source_dir: Path,
    staging: Path,
    files: Sequence[Path],
    native_paths: set[PurePosixPath],
    reject_packed_directory: str | None = None,
) -> None:
    for source in files:
        relative = source.relative_to(source_dir)
        if PurePosixPath(relative.as_posix()) in native_paths:
            raise ValueError(f"native sidecar must be supplied by the Factory recipe, not source: {relative}")
        if reject_packed_directory and relative.parts and relative.parts[0] == reject_packed_directory:
            raise ValueError(f"packed browser runtime must be supplied by the Factory recipe, not source: {relative}")
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def install_packed_runtime(
    staging: Path, recipe: NativeSidecarRecipe, target: NativeTarget, runtime: PackedRuntimeInput
) -> None:
    """Copy a prevalidated runtime and write its immutable in-artifact index."""

    destination_root = staging / packed_runtime_directory(recipe)
    if destination_root.exists():
        raise ValueError("staged plugin unexpectedly already contains packed runtime")
    for source in sorted(runtime.root.rglob("*")):
        relative = source.relative_to(runtime.root)
        destination = destination_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    copied_manifest, _ = packed_runtime_manifest(recipe, destination_root, target)
    if copied_manifest != runtime.manifest:
        raise ValueError("packed runtime changed while the Factory staged it")
    if recipe.packed_runtime_kind == "browser-node":
        node = destination_root / browser_runtime_node_path(target)
        node.chmod(0o755)
    (destination_root / "manifest.json").write_bytes(runtime.manifest)


def rewrite_mcp_command(staging: Path, recipe: NativeSidecarRecipe, target: NativeTarget) -> None:
    """Use the executable filename expected by this platform artifact."""

    if archive_path_for(recipe, target) == recipe.archive_path:
        return
    path = staging / "mcp.json"
    try:
        document = json.loads(read_regular_mcp(path, f"staged {recipe.plugin_id} mcp.json"))
        servers = document["mcpServers"]
        for server in recipe.servers:
            servers[server.server_id]["command"] = mcp_command_for(recipe, target)
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot stage platform MCP declaration for {recipe.plugin_id}: {error}") from error
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def target_for(recipe: NativeSidecarRecipe, rust_target: str) -> NativeTarget:
    for target in recipe.targets:
        if target.rust_target == rust_target:
            return target
    raise ValueError(f"native sidecar target is not allowlisted: {recipe.plugin_id}@{rust_target}")


def archive_member_is_regular_file(member: object) -> bool:
    is_directory = getattr(member, "is_dir", lambda: False)()
    mode = int(getattr(member, "external_attr", 0)) >> 16
    return not is_directory and stat.S_IFMT(mode) in {0, stat.S_IFREG}


def archive_member_is_executable(member: object) -> bool:
    return archive_member_is_regular_file(member) and bool((int(getattr(member, "external_attr", 0)) >> 16) & 0o111)


def validate_native_archive(
    plugin_id: str,
    archive_members: Mapping[str, object],
    mcp_bytes: bytes | None,
    os_name: str,
    arch: str,
    packed_runtime_manifest: bytes | None = None,
    packed_runtime_digests: Mapping[str, str] | None = None,
) -> bool:
    """Validate a native artifact's platform and required portable entrypoint.

    ``archive_members`` is intentionally opaque to keep ZIP-library handling at
    the caller. The native entrypoint itself must still be a regular file.
    """

    if "mcp.json" not in archive_members:
        return False
    mcp_member = archive_members["mcp.json"]
    if not archive_member_is_regular_file(mcp_member):
        raise ValueError(f"native MCP artifact mcp.json must be a regular file: {plugin_id}")
    if mcp_bytes is None:
        raise ValueError(f"native MCP artifact cannot read mcp.json: {plugin_id}")
    if not declares_stdio_server(mcp_bytes, f"artifact {plugin_id} mcp.json"):
        raise ValueError(f"native MCP artifact must declare a stdio server: {plugin_id}")
    recipe = RECIPES.get(plugin_id)
    if recipe is None:
        raise ValueError(f"native MCP artifact is not on the Factory allowlist: {plugin_id}")
    target = next((item for item in recipe.targets if item.os_name == os_name and item.arch == arch), None)
    if target is None:
        raise ValueError(f"native MCP artifact has unsupported target {os_name}/{arch}: {plugin_id}")
    validate_mcp_declaration(recipe, mcp_bytes, f"artifact {plugin_id} mcp.json", target)
    entrypoint = archive_path_for(recipe, target).as_posix()
    member = archive_members.get(entrypoint)
    if member is None:
        raise ValueError(f"native MCP artifact is missing {entrypoint}: {plugin_id}")
    if not archive_member_is_regular_file(member):
        raise ValueError(f"native MCP artifact entrypoint must be a regular file: {plugin_id}")
    if not archive_member_is_executable(member):
        raise ValueError(f"native MCP artifact entrypoint must be executable: {plugin_id}")
    if recipe.requires_packed_runtime:
        validate_packed_runtime_archive(
            recipe,
            archive_members,
            target,
            packed_runtime_manifest,
            packed_runtime_digests or {},
        )
    return True


def validate_packed_runtime_archive(
    recipe: NativeSidecarRecipe,
    archive_members: Mapping[str, object],
    target: NativeTarget,
    manifest_bytes: bytes | None,
    file_digests: Mapping[str, str],
) -> None:
    if recipe.packed_runtime_kind == "browser-node":
        validate_packed_browser_runtime_archive(archive_members, target, manifest_bytes, file_digests)
        return
    if recipe.packed_runtime_kind == "binary-engine":
        validate_packed_binary_engine_archive(archive_members, target, manifest_bytes, file_digests)
        return
    raise ValueError(f"native artifact has an unsupported packed runtime: {recipe.plugin_id}")


def validate_packed_browser_runtime_archive(
    archive_members: Mapping[str, object],
    target: NativeTarget,
    manifest_bytes: bytes | None,
    file_digests: Mapping[str, str],
) -> None:
    """Verify the packaged runtime index before Desktop trusts its sidecar."""

    expected = parse_packed_runtime_manifest(manifest_bytes, target)
    validate_packed_runtime_members(archive_members, expected, file_digests)
    actual = {
        name.removeprefix("runtime/")
        for name, member in archive_members.items()
        if name.startswith("runtime/")
        and name != "runtime/manifest.json"
        and archive_member_is_regular_file(member)
    }
    if actual != set(expected):
        raise ValueError("browser runtime archive members do not match manifest.json")
    node = f"runtime/{browser_runtime_node_path(target).as_posix()}"
    node_member = archive_members.get(node)
    if node_member is None or not archive_member_is_executable(node_member):
        raise ValueError("browser runtime Node executable is missing or not executable")
    required = {
        "runtime/node-version.txt",
        f"runtime/node_modules/playwright-core/package.json",
        f"runtime/node_modules/cloakbrowser/package.json",
        *(f"runtime/bridge/{name}" for name in BROWSER_BRIDGE_FILES),
    }
    if not required.issubset(archive_members):
        raise ValueError("browser runtime is missing Playwright or CloakBrowser")


def validate_packed_binary_engine_archive(
    archive_members: Mapping[str, object],
    target: NativeTarget,
    manifest_bytes: bytes | None,
    file_digests: Mapping[str, str],
) -> None:
    expected = parse_binary_engine_manifest(manifest_bytes, target)
    validate_packed_runtime_members(
        archive_members, expected, file_digests, "engine", "binary engine"
    )
    index = archive_members.get("engine/manifest.json")
    if index is None or not archive_member_is_regular_file(index):
        raise ValueError("binary engine manifest is missing or non-regular")
    executable = "engine/radare2/bin/r2.exe" if target.os_name == "windows" else "engine/radare2/bin/r2"
    member = archive_members.get(executable)
    if member is None or not archive_member_is_executable(member):
        raise ValueError(f"binary engine entrypoint is missing or not executable: {executable}")


def parse_packed_runtime_manifest(
    manifest_bytes: bytes | None,
    target: NativeTarget,
) -> dict[str, tuple[int, str]]:
    if manifest_bytes is None:
        raise ValueError("browser native artifact is missing runtime/manifest.json")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"browser runtime manifest is invalid: {error}") from error
    if not isinstance(manifest, dict) or set(manifest) != {"schemaVersion", "platform", "nodeVersion", "files"}:
        raise ValueError("browser runtime manifest has an unsupported schema")
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("platform") != browser_runtime_platform(target)
        or manifest.get("nodeVersion") != BROWSER_NODE_VERSION
    ):
        raise ValueError("browser runtime manifest does not match the artifact platform")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("browser runtime manifest must enumerate regular files")
    expected: dict[str, tuple[int, str]] = {}
    for item in files:
        path, size, digest = runtime_manifest_file(item)
        if path in expected:
            raise ValueError("browser runtime manifest contains duplicate file paths")
        expected[path] = (size, digest)
    return expected


def parse_binary_engine_manifest(
    manifest_bytes: bytes | None, target: NativeTarget
) -> dict[str, tuple[int, str]]:
    if manifest_bytes is None:
        raise ValueError("binary-analysis artifact is missing engine/manifest.json")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"binary engine manifest is invalid: {error}") from error
    expected_keys = {
        "schemaVersion", "platform", "engineVersions", "sourcePins", "sourcePatchSets",
        "licenseInventorySha256", "files",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise ValueError("binary engine manifest has an unsupported schema")
    if (
        type(manifest.get("schemaVersion")) is not int
        or manifest.get("schemaVersion") != BINARY_ENGINE_MANIFEST_SCHEMA_VERSION
        or manifest.get("platform") != browser_runtime_platform(target)
    ):
        raise ValueError("binary engine manifest does not match the artifact platform")
    if manifest.get("engineVersions") != BINARY_ANALYSIS_ENGINE_VERSIONS:
        raise ValueError("binary engine manifest versions do not match the approved baseline")
    if manifest.get("sourcePins") != BINARY_ANALYSIS_SOURCE_PINS:
        raise ValueError("binary engine manifest source pins do not match the approved baseline")
    if manifest.get("sourcePatchSets") != BINARY_ANALYSIS_SOURCE_PATCHSETS:
        raise ValueError("binary engine manifest source patch sets do not match the approved baseline")
    inventory_digest = manifest.get("licenseInventorySha256")
    if not isinstance(inventory_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", inventory_digest):
        raise ValueError("binary engine manifest license inventory digest is invalid")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("binary engine manifest must enumerate regular files")
    if len(files) > MAX_BINARY_ENGINE_FILES:
        raise ValueError("binary engine manifest exceeds the 4,096-file limit")
    expected: dict[str, tuple[int, str]] = {}
    total_bytes = 0
    for item in files:
        path, size, digest = runtime_manifest_file(item, MAX_BINARY_ENGINE_BYTES)
        if path in expected:
            raise ValueError("binary engine manifest contains duplicate file paths")
        expected[path] = (size, digest)
        total_bytes += size
        if total_bytes > MAX_BINARY_ENGINE_BYTES:
            raise ValueError("binary engine manifest exceeds the 100 MiB size limit")
    if expected.get(BINARY_ENGINE_LICENSE_INVENTORY, (0, ""))[1] != inventory_digest:
        raise ValueError("binary engine manifest license inventory digest mismatch")
    require_binary_engine_manifest_components(expected, target)
    return expected


def runtime_manifest_file(
    item: object, max_file_bytes: int = MAX_BROWSER_RUNTIME_FILE_BYTES
) -> tuple[str, int, str]:
    if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
        raise ValueError("browser runtime manifest file record is invalid")
    path, digest, size = item.get("path"), item.get("sha256"), item.get("size")
    relative = PurePosixPath(path) if isinstance(path, str) else None
    if (
        relative is None or not path or relative.is_absolute() or ".." in relative.parts
        or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or type(size) is not int or size <= 0 or size > max_file_bytes
        or relative.as_posix() != path or "\\" in path
    ):
        raise ValueError("browser runtime manifest contains an unsafe file record")
    return path, size, digest


def validate_packed_runtime_members(
    archive_members: Mapping[str, object],
    expected: Mapping[str, tuple[int, str]],
    file_digests: Mapping[str, str],
    runtime_directory: str = "runtime",
    label: str = "browser runtime",
) -> None:
    for path, (size, digest) in expected.items():
        archive_path = f"{runtime_directory}/{PurePosixPath(path).as_posix()}"
        member = archive_members.get(archive_path)
        if member is None or not archive_member_is_regular_file(member):
            raise ValueError(f"{label} member is absent or non-regular: {archive_path}")
        if getattr(member, "file_size", None) != size or file_digests.get(archive_path) != digest:
            raise ValueError(f"{label} member digest mismatch: {archive_path}")
    actual = {
        name.removeprefix(f"{runtime_directory}/")
        for name, member in archive_members.items()
        if name.startswith(f"{runtime_directory}/")
        and name != f"{runtime_directory}/manifest.json"
        and archive_member_is_regular_file(member)
    }
    if actual != set(expected):
        raise ValueError(f"{label} archive members do not match manifest.json")
