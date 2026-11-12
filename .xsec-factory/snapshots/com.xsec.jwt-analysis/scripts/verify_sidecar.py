from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {"jwt_analysis_create", "jwt_analysis_diagnostics", "jwt_analysis_report"}


def verify(binary: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="xsec-jwt-sidecar-") as data_dir:
        env = {**os.environ, "PLUGIN_DATA": data_dir, "PLUGIN_ROOT": str(ROOT)}
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "jwt_analysis_diagnostics", "arguments": {}}}]
        process = subprocess.run([str(binary)], input="\n".join(map(json.dumps, requests)) + "\n",
                                 text=True, capture_output=True, env=env, check=True, timeout=30)
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    names = {item["name"] for item in replies[1]["result"]["tools"]}
    assert EXPECTED_TOOLS <= names
    assert replies[2]["result"]["structuredContent"]["jwt_tool_version"] == "2.3.0"
    assert replies[2]["result"]["structuredContent"]["sidecar"] == "ready"


if __name__ == "__main__":
    verify(Path(sys.argv[1]).resolve())
    print("JWT Analysis Sidecar smoke check passed")
