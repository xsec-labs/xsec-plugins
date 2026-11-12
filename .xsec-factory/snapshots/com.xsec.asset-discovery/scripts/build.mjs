import { build } from "esbuild";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const pluginRoot = new URL("../", import.meta.url);
const frontendOutput = new URL("com.xsec.desktop/frontend/index.js", pluginRoot);

function addExplicitActivatorExport(source) {
  const functionMarker = "function activate(host){";
  const exportMarker = "export{activate};";
  const parts = source.split(functionMarker);
  if (parts.length !== 2 || !parts[1].endsWith(exportMarker + "\n")) {
    throw new Error("Expected the generated frontend activator export");
  }
  return `${parts[0]}export function activate(host) {${parts[1].slice(0, -exportMarker.length - 1).trimEnd()}\n`;
}

const result = await build({
  absWorkingDir: pluginRoot.pathname,
  entryPoints: [new URL("frontend-src/index.tsx", pluginRoot).pathname],
  outfile: frontendOutput.pathname,
  bundle: true,
  format: "esm",
  target: ["es2022"],
  jsx: "automatic",
  loader: { ".css": "text" },
  define: { "process.env.NODE_ENV": '"production"' },
  minifyIdentifiers: false,
  minifySyntax: false,
  minifyWhitespace: true,
  legalComments: "none",
  metafile: true,
  banner: { js: "/*! Third-party licenses: ../THIRD_PARTY_NOTICES.txt */" },
});

const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.includes("node_modules/")) continue;
  let directory = dirname(resolve(pluginRoot.pathname, input));
  while (true) {
    const metadataPath = join(directory, "package.json");
    if (existsSync(metadataPath)) {
      const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
      if (typeof metadata.name === "string" && typeof metadata.version === "string") {
        packages.set(metadata.name + "@" + metadata.version, directory);
        break;
      }
    }
    const parent = dirname(directory);
    if (parent === directory) throw new Error("Cannot identify a bundled dependency: " + input);
    directory = parent;
  }
}
for (const output of Object.values(result.metafile.outputs)) {
  if (output.imports.some(entry => entry.external)) throw new Error("Plugin frontend contains an external module import");
}
const notices = ["Third-party licenses for the asset-discovery frontend\n"];
for (const [name, directory] of [...packages].sort(([left], [right]) => left.localeCompare(right, "en"))) {
  const files = (await readdir(directory)).filter(file => /^licen[cs]e(?:[._-].*)?$/i.test(file)).sort();
  if (!files.length) throw new Error("Bundled dependency license is missing: " + name);
  notices.push("\n## " + name + "\n");
  for (const file of files) notices.push(await readFile(join(directory, file), "utf8"));
  const attribution = join(directory, "THIRD_PARTY_NOTICES.md");
  if (existsSync(attribution)) notices.push(await readFile(attribution, "utf8"));
}
await writeFile(new URL("com.xsec.desktop/THIRD_PARTY_NOTICES.txt", pluginRoot), notices.join("\n") + "\n", "utf8");

const bundle = await readFile(frontendOutput, "utf8");
await writeFile(frontendOutput, addExplicitActivatorExport(bundle), "utf8");
