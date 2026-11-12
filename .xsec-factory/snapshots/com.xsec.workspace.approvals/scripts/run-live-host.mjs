import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const cli = process.env.TAURI_MCP_CLI;
if (!cli) throw new Error("Set TAURI_MCP_CLI to the installed @hypothesi/tauri-mcp-cli dist/index.js");
const options = JSON.parse(readFileSync(process.argv[2], "utf8"));
const source = readFileSync(new URL("./verify-live-host.mjs", import.meta.url), "utf8").replace("export async function", "async function");
const script = `(() => { ${source}; window.approvalHostRegression = {status:'running'};
verifyLiveHost(${JSON.stringify(options)}).then(result => {window.approvalHostRegression = result;}, error => {window.approvalHostRegression = {passed:false,error:String(error)};}); return 'started'; })()`;
const result = execFileSync(process.execPath, [cli, "webview-execute-js", "--script", script], { encoding: "utf8" });
process.stdout.write(result);
console.log('Read window.approvalHostRegression with webview-execute-js when execution completes.');
