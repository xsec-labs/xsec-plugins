from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["PLUGIN_ROOT"] = str(ROOT)

from jwt_analysis_mcp import jwt, probe
from jwt_analysis_mcp.engine import run_job
from jwt_analysis_mcp.http_request import RawHttp, RequestLimiter
from jwt_analysis_mcp.store import Store


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def token(secret: bytes) -> str:
    body = b64(b'{"alg":"HS256","typ":"JWT"}') + "." + b64(b'{"sub":"alice","exp":4102444800}')
    signature = hmac.new(secret, body.encode(), hashlib.sha256).digest()
    return body + "." + b64(signature)


class Target(BaseHTTPRequestHandler):
    expected = ""

    def do_GET(self) -> None:
        accepted = self.headers.get("Authorization") == "Bearer " + self.expected
        body = b"principal=alice canary=xsec-check" if accepted else b"unauthorized"
        self.send_response(200 if accepted else 401)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def check_mcp_protocol() -> None:
    with tempfile.TemporaryDirectory(prefix="xsec-jwt-mcp-") as data_dir:
        env = {**os.environ, "PLUGIN_DATA": data_dir, "PYTHONPATH": str(ROOT / "src"),
               "XSEC_PLUGIN_HOST_RPC_ENDPOINT": "http://127.0.0.1:1/plugin-host-rpc"}
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "jwt_analysis_diagnostics", "arguments": {}}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "jwt_analysis_create", "arguments": {"source": {"kind": "token", "token": "x"}}}}]
        process = subprocess.run([sys.executable, "-m", "jwt_analysis_mcp"], input="\n".join(map(json.dumps, requests)) + "\n",
                                 text=True, capture_output=True, cwd=ROOT, env=env, check=True)
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    names = {tool["name"] for tool in replies[1]["result"]["tools"]}
    assert replies[0]["result"]["serverInfo"]["name"] == "xsec-jwt-analysis"
    assert replies[0]["result"]["serverInfo"]["version"] == "1.0.0"
    assert {"jwt_analysis_create", "jwt_analysis_evidence_get", "jwt_analysis_delete"} <= names
    assert replies[2]["result"]["isError"] is False
    assert replies[3]["result"]["isError"] is True


def check_database_and_secret_adapter(temp: Path) -> None:
    secret = b"jwt-tool-fixture-secret"
    signed = token(secret)
    dictionary = temp / "custom.txt"
    dictionary.write_bytes(b"wrong\n" + secret + b"\n")
    os.environ["PLUGIN_DATA"] = str(temp / "data")
    store = Store(os.environ["PLUGIN_DATA"])
    source = {"items": [{"token": signed, "source": "test"}], "profile": "passive"}
    job_id = store.create_job("project-a", "passive", source)
    settings = {"wordlists": ["custom"], "custom_wordlists": [str(dictionary)]}
    run_job(job_id, source, settings, store, lambda: store.cancelled(job_id))
    job = store.job("project-a", job_id)
    weak = next(item for item in job["tests"] if item["test_id"] == "weak-secret")
    assert job["status"] == "completed" and weak["status"] == "vulnerable"
    assert weak["details"]["key_masked"] != secret.decode()
    try:
        store.job("project-b", job_id)
    except ValueError:
        pass
    else:
        raise AssertionError("cross-project job read was accepted")
    evidence = store.evidence_get("project-a", weak["evidence_id"], False)
    assert evidence["evidence"]["secret"] == "[REDACTED]"
    from jwt_analysis_mcp.store import _redact
    assert _redact({"headers": [["Authorization", "Bearer abc.def.ghi"]]}, "standard")["headers"][0][1] == "[REDACTED]"
    second = store.create_job("project-a", "passive", source)
    store.token(second, signed, jwt.parse(signed))
    assert len(store.job("project-a", second)["tokens"]) == 1
    malformed = store.create_job("project-a", "passive", {"items": [{"token": "bad", "source": "test"}], "profile": "passive"})
    run_job(malformed, {"items": [{"token": "bad", "source": "test"}], "profile": "passive"}, settings, store,
            lambda: store.cancelled(malformed))
    invalid = store.job("project-a", malformed)
    assert invalid["status"] == "error" and invalid["tests"][0]["status"] == "error"
    interrupted = store.create_job("project-a", "passive", source)
    store.recover_interrupted()
    assert store.job("project-a", interrupted)["status"] == "error"
    cancelled = store.create_job("project-a", "passive", source)
    assert store.cancel("project-a", cancelled)
    assert store.job("project-a", cancelled)["status"] == "cancelled"
    store.delete("project-a", cancelled)


def check_loopback_http(temp: Path) -> None:
    signed = token(b"unlisted-secret")
    Target.expected = signed
    server = HTTPServer(("127.0.0.1", 0), Target)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(str(temp / "http-data"))
    parsed = jwt.parse(signed)
    job_id = store.create_job("project-a", "full", {"items": []})
    raw = (f"GET /check HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
           f"Authorization: Bearer {signed}\r\n\r\n")
    response = RawHttp({"rate_limit": 60, "request_timeout_seconds": 3}, RequestLimiter({"rate_limit": 60})).send(raw, "http")
    assert response["status"] == 200 and "canary=xsec-check" in response["body"]
    source = {"canary": "canary=xsec-check"}
    probe.run_active(job_id, {"token": signed, "request": raw, "scheme": "http"}, parsed,
                     None, {"rate_limit": 60, "request_timeout_seconds": 3}, source, store, lambda: False)
    job = store.job("project-a", job_id)
    statuses = {item["test_id"]: item["status"] for item in job["tests"]}
    assert statuses["alg-none"] == "not_vulnerable" and statuses["baseline"] == "not_vulnerable"
    assert statuses["blank-password"] == statuses["blank-password-2"] == "not_vulnerable"
    assert statuses["header-kid"] == statuses["header-jwk"] == "not_vulnerable"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def check_parser_and_rockyou() -> None:
    signed = token(b"x")
    parsed = jwt.parse(signed)
    assert parsed["payload"]["sub"] == "alice"
    variants = probe._variants(parsed, b"x", {"public_key": ""})
    assert any(item[0] == "alg-none-mixedcase" for item in variants)
    assert len([item for item in variants if item[0].startswith("common-claim:")]) == 60
    try:
        jwt.parse("bad.jwt.value")
    except ValueError:
        pass
    else:
        raise AssertionError("malformed JWT accepted")
    first = next(probe_wordlist())
    assert first


def probe_wordlist():
    from jwt_analysis_mcp.engine import _read_wordlist
    return _read_wordlist("rockyou", ROOT / "wordlists" / "rockyou.txt.tar.gz")


def main() -> None:
    check_parser_and_rockyou()
    check_mcp_protocol()
    with tempfile.TemporaryDirectory(prefix="xsec-jwt-check-") as directory:
        temp = Path(directory)
        check_database_and_secret_adapter(temp)
        check_loopback_http(temp)
    print("JWT Sidecar checks passed: MCP stdio, SQLite isolation, jwt_tool secret check, loopback HTTP")


if __name__ == "__main__":
    main()
