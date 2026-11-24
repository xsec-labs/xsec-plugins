// Manifest, entrypoint and permission checks for this plugin package.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Bump this together with the manifest's extensions["com.xsec.desktop"].schemaVersion.
const EXPECTED_SCHEMA_VERSION = 3;

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const readJson = (path) => JSON.parse(readFileSync(join(root, path), "utf8"));
const plugin = readJson("plugin.json");
const catalog = readJson(".codex-plugin/plugin.json");
const extension = plugin.extensions["com.xsec.desktop"];

test("the two manifests describe the same plugin", () => {
  assert.equal(catalog.name, plugin.name);
  assert.equal(catalog.version, plugin.version);
});

test("the Desktop extension declares the expected schema version", () => {
  assert.equal(extension.schemaVersion, EXPECTED_SCHEMA_VERSION);
});

test("every file entrypoint exists and is not empty", () => {
  for (const [kind, value] of Object.entries(extension.entrypoints ?? {})) {
    if (value.startsWith("builtin:")) continue;
    const file = join(root, value);
    assert.ok(existsSync(file), `${kind} entrypoint ${value} is missing`);
    assert.ok(readFileSync(file).length > 0, `${kind} entrypoint ${value} is empty`);
  }
});

test("every frontend capability and agent tool permission is declared", () => {
  const declared = new Set(Object.keys(extension.permissions ?? {}));
  for (const method of Object.values(extension.frontendApi?.methods ?? {})) {
    assert.ok(declared.has(method.capability), `frontend method needs undeclared ${method.capability}`);
  }
  for (const binding of Object.values(extension.contributes?.agentTools ?? {})) {
    assert.ok(declared.has(binding.permission), `agent tool ${binding.mcpTool} needs undeclared ${binding.permission}`);
  }
});

test("the MCP server declaration parses when present", () => {
  if (!existsSync(join(root, "mcp.json"))) return;
  assert.ok(readJson("mcp.json").mcpServers, "mcp.json has no mcpServers");
});
