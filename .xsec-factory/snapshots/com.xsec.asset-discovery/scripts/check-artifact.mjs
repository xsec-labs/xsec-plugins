import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const SEMVER_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;
const NATIVE_PERMISSIONS = ["mcp.servers.register", "native.execute"];
const MCP_SERVERS = ["asset-fofa", "asset-hunter", "asset-normalize"];
const artifact = new URL("../com.xsec.desktop/frontend/index.js", import.meta.url);
const manifestPath = new URL("../plugin.json", import.meta.url);
const codexManifestPath = new URL("../.codex-plugin/plugin.json", import.meta.url);
const packagePath = new URL("../package.json", import.meta.url);
const mcpPath = new URL("../mcp.json", import.meta.url);
const skillPath = new URL("../skills/asset-discovery/SKILL.md", import.meta.url);
const source = await readFile(artifact, "utf8");
const frontendBytes = Buffer.byteLength(source, "utf8");
const frontendLimitBytes = 4 * 1024 * 1024;
if (frontendBytes > frontendLimitBytes) throw new Error("Plugin frontend exceeds the Desktop Host 4 MiB source limit");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const codexManifest = JSON.parse(await readFile(codexManifestPath, "utf8"));
const packageMetadata = JSON.parse(await readFile(packagePath, "utf8"));
const mcp = JSON.parse(await readFile(mcpPath, "utf8"));
const skill = await readFile(skillPath, "utf8");
const release = JSON.parse(await readFile(new URL("../vendor/xsec-ui/release.json", import.meta.url), "utf8"));
if (release.schemaVersion !== 1 || release.packages?.length !== 2) throw new Error("Invalid shared UI release manifest");
for (const pkg of release.packages) {
  const bytes = await readFile(new URL("../vendor/xsec-ui/" + pkg.file, import.meta.url));
  if (createHash("sha256").update(bytes).digest("hex") !== pkg.sha256) throw new Error("Shared UI package digest mismatch: " + pkg.name);
  if (packageMetadata.dependencies?.[pkg.name] !== "file:vendor/xsec-ui/" + pkg.file) throw new Error("Shared UI dependency differs from release manifest: " + pkg.name);
}
const notices = await readFile(new URL("../com.xsec.desktop/THIRD_PARTY_NOTICES.txt", import.meta.url), "utf8");
for (const name of ["@xsec/design-tokens@", "@xsec/ui-react@", "@base-ui/react@", "react@", "react-dom@", "motion@", "lucide-react@", "Saurabh Chauhan"]) {
  if (!notices.includes(name)) throw new Error("Plugin frontend attribution is missing: " + name);
}
if (!source.includes("THIRD_PARTY_NOTICES.txt") || !source.includes("data-xui-theme")) throw new Error("Plugin shared UI artifact is incomplete");

if (!source.includes("export function activate(host)") || /from\s*["']\.?\//.test(source)) {
  throw new Error("资产发现前端制品必须是单一 ESM 模块");
}
const releaseVersions = [manifest.version, codexManifest.version, packageMetadata.version];
if (!releaseVersions.every((version) => typeof version === "string" && SEMVER_PATTERN.test(version)) || new Set(releaseVersions).size !== 1) {
  throw new Error("资产发现发布元数据必须使用一致的有效 SemVer 版本");
}
const desktop = manifest.extensions?.["com.xsec.desktop"];
if (desktop?.schemaVersion !== 2 || !NATIVE_PERMISSIONS.every((permission) => desktop.permissions?.[permission])) {
  throw new Error("资产发现必须声明 schema v2 原生 MCP 权限");
}
const servers = Object.keys(mcp.mcpServers ?? {}).sort();
if (JSON.stringify(servers) !== JSON.stringify(MCP_SERVERS)) {
  throw new Error("资产发现 MCP server 集合不正确");
}
const agentTools = desktop.contributes?.agentTools ?? {};
if (!MCP_SERVERS.every((server) => Object.values(agentTools).some((tool) => tool?.mcpServer === server))) {
  throw new Error("资产发现必须公开每个 MCP server 的受限 Agent Tool");
}
if (!skill.startsWith("---\nname: asset-discovery\n")) {
  throw new Error("资产发现 Skill frontmatter 不正确");
}
console.log(JSON.stringify({ plugin: manifest.name, version: manifest.version, frontendBytes, frontendLimitBytes, frontendSha256: createHash("sha256").update(source).digest("hex"), sharedPackages: release.packages, attribution: "com.xsec.desktop/THIRD_PARTY_NOTICES.txt", status: "passed" }));
