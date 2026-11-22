import { chmod, copyFile, mkdir, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const binary = process.platform === "win32" ? "system-terminal-mcp.exe" : "system-terminal-mcp";
const cargoTarget = process.env.CARGO_TARGET_DIR
  ? resolve(process.env.CARGO_TARGET_DIR)
  : resolve(root, "target");
const source = resolve(cargoTarget, "release", binary);
const destination = resolve(root, "bin", binary);

await run("cargo", ["build", "--locked", "--release"], root);
const sourceMetadata = await stat(source);
if (!sourceMetadata.isFile()) throw new Error(`未找到编译后的 system-terminal MCP: ${source}`);
await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
if (process.platform !== "win32") await chmod(destination, 0o755);
process.stdout.write(`${destination}\n`);

function run(command, args, cwd) {
  return new Promise((resolveRun, reject) => {
    const child = spawn(command, args, { cwd, shell: false, stdio: "inherit" });
    child.once("error", (error) => reject(new Error(`启动 ${command} 失败: ${error.message}`)));
    child.once("exit", (code, signal) => code === 0
      ? resolveRun()
      : reject(new Error(`${command} 失败: ${signal ?? `exit ${code}`}`)));
  });
}
