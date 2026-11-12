from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import engine, jwt
from .reports import report
from .runner import JobRunner, record_failure
from .settings import DEFAULTS, merge as merge_settings
from .store import Store
from .tool_schemas import MAX_LIST_LIMIT, TOOLS
from .jwt_tool_adapter import diagnostics as runtime_diagnostics, module as upstream_module


SERVER_NAME = "xsec-jwt-analysis"
PROTOCOL_VERSION = "2025-03-26"
CONTEXT_KEY = "com.xsec.desktop/contextHandle"
MAX_BATCH_ITEMS = 100
MAX_RPC_LINE_BYTES = 4 * 1024 * 1024
def main() -> None:
    _store().recover_interrupted()
    upstream_module()
    for line in sys.stdin:
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > MAX_RPC_LINE_BYTES:
            raise ValueError("MCP request exceeds the 4 MiB input limit")
        request = json.loads(line)
        response = _handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False) + "\n")
            sys.stdout.flush()


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method, request_id = request.get("method"), request.get("id")
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    if method == "initialize":
        version = request.get("params", {}).get("protocolVersion", PROTOCOL_VERSION)
        return _rpc_result(request_id, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                                         "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"}})
    if method == "ping":
        return _rpc_result(request_id, {})
    if method == "tools/list":
        return _rpc_result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = request.get("params", {})
        try:
            result = call_tool(params.get("name", ""), params.get("arguments", {}), params.get("_meta", {}))
            return _rpc_result(request_id, {"content": [{"type": "text", "text": _json(result)}],
                                "structuredContent": result, "isError": False})
        except (ValueError, PermissionError, OSError, urllib.error.URLError) as error:
            message = str(error) if isinstance(error, (ValueError, PermissionError)) else type(error).__name__
            return _rpc_result(request_id, {"content": [{"type": "text", "text": message}], "isError": True})
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}}


def call_tool(name: str, args: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    tool = next((entry for entry in TOOLS if entry["name"] == name), None)
    if tool is None:
        raise ValueError("unknown JWT analysis tool")
    if name == "jwt_analysis_diagnostics":
        return runtime_diagnostics()
    identity = host_call("xsec.jwt-analysis.context", {"tool": name}, meta)
    project_id = identity.get("projectId")
    if not isinstance(project_id, str) or not project_id:
        raise PermissionError("JWT analysis requires a trusted project context")
    store = _store()
    if name == "jwt_analysis_create":
        return _create(args, meta, identity, store)
    if name == "jwt_analysis_list":
        return {"items": store.list_jobs(project_id, _limit(args.get("limit"), 50))}
    if name == "jwt_analysis_get":
        return store.job(project_id, _required_string(args, "job_id"))
    if name == "jwt_analysis_events":
        return store.events(project_id, _required_string(args, "job_id"), _limit(args.get("cursor"), 0), 200)
    if name == "jwt_analysis_cancel":
        job_id = _required_string(args, "job_id")
        RUNNER.cancel_pending(job_id)
        if not store.cancel(project_id, job_id):
            raise ValueError("job is not queued or running in this project")
        return {"job_id": job_id, "status": "cancellation_requested"}
    if name == "jwt_analysis_retry":
        return _retry(project_id, _required_string(args, "job_id"), meta, name, store)
    if name == "jwt_analysis_evidence_get":
        reveal = args.get("include_sensitive", False)
        if not isinstance(reveal, bool):
            raise ValueError("include_sensitive must be a boolean")
        settings = _settings(meta, name)
        return store.evidence_get(project_id, _required_string(args, "evidence_id"), reveal,
                                  settings.get("evidence_redaction", "standard"))
    if name == "jwt_analysis_report":
        job = store.job(project_id, _required_string(args, "job_id"))
        return report(job, args.get("format", "markdown"))
    if name == "jwt_analysis_delete":
        job_id = _required_string(args, "job_id")
        store.delete(project_id, job_id)
        return {"job_id": job_id, "deleted": True}
    raise ValueError("unsupported JWT analysis tool")


def _create(args: dict[str, Any], meta: dict[str, Any], identity: dict[str, Any], store: Store) -> dict[str, Any]:
    tool = "jwt_analysis_create"
    settings = _settings(meta, tool)
    source = _normalize_source(args, meta, identity, settings)
    profile = args.get("profile", "full")
    if profile not in ("full", "passive"):
        raise ValueError("profile must be full or passive")
    selected = args.get("wordlists", settings.get("wordlists", DEFAULTS["wordlists"]))
    if not isinstance(selected, list) or any(item not in ("jwt-common", "rockyou", "custom") for item in selected):
        raise ValueError("wordlists contains an unsupported dictionary id")
    custom = args.get("custom_wordlists", settings.get("custom_wordlists", []))
    if not isinstance(custom, list) or any(not isinstance(path, str) for path in custom):
        raise ValueError("custom_wordlists must be an array of configured paths")
    permitted = set(settings.get("custom_wordlists", []))
    if any(path not in permitted for path in custom):
        raise PermissionError("custom wordlists must first be configured in JWT Analysis settings")
    settings = {**settings, "wordlists": selected, "custom_wordlists": custom,
                "rate_limit": _bounded(args.get("rate_limit", settings.get("rate_limit", 10)), 1, 60, "rate_limit")}
    request, scheme = _request_value(args.get("request"), args.get("scheme"))
    canary = args.get("canary", "")
    if not isinstance(canary, str) or len(canary) > 2048:
        raise ValueError("canary must be a string no longer than 2 KiB")
    if request:
        for item in source["items"]:
            item["request"] = jwt.replace_token(request, item["token"], item["token"])
            item["scheme"] = scheme
    source.update({"profile": profile, "canary": canary, "request": request, "scheme": scheme})
    _validate_items(source["items"])
    job_id = store.create_job(identity["projectId"], profile, source)
    action = lambda: engine.run_job(job_id, source, settings, store, lambda: store.cancelled(job_id))
    RUNNER.submit(job_id, action, _bounded(settings.get("max_concurrent_jobs", 2), 1, 8, "max_concurrent_jobs"))
    return {"job_id": job_id, "status": "queued", "project_id": identity["projectId"],
            "token_fingerprints": [item["fingerprint"] for item in source["items"]],
            "workspace_tool_id": "jwt-analysis"}


def _normalize_source(args: dict[str, Any], meta: dict[str, Any], identity: dict[str, Any],
                      settings: dict[str, Any]) -> dict[str, Any]:
    source = args.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    kind = source.get("kind")
    items: list[dict[str, Any]] = []
    if kind == "token":
        token = source.get("token", "")
        if not isinstance(token, str):
            raise ValueError("source.token must be a string")
        tokens = jwt.extract_tokens(token) or ([token.strip()] if token.strip() else [])
        items.extend({"token": item, "source": "token"} for item in tokens)
    elif kind == "batch":
        values = source.get("items", [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("source.items must be an array of strings")
        if len(values) > MAX_BATCH_ITEMS:
            raise ValueError("batch exceeds 100 tokens")
        for value in values:
            tokens = jwt.extract_tokens(value) or ([value.strip()] if value.strip() else [])
            items.extend({"token": item, "source": "batch"} for item in tokens)
    elif kind == "traffic_ref":
        flow = host_call("xsec.jwt-analysis.traffic_get", {"tool": "jwt_analysis_create", "flowId": source.get("flow_id")}, meta)
        raw = flow["rawRequest"]
        items.extend({"token": token, "request": raw, "scheme": flow["scheme"], "source": "traffic_ref"}
                     for token in jwt.extract_tokens(raw))
    elif kind in ("project_file", "request_file"):
        file = host_call("xsec.jwt-analysis.project_file_get", {"tool": "jwt_analysis_create", "path": source.get("path")}, meta)
        content = file["content"]
        items.extend({"token": token, "source": kind} for token in jwt.extract_tokens(content))
        if kind == "request_file":
            request, scheme = _request_value(content, args.get("scheme"))
            for item in items:
                item["request"], item["scheme"] = jwt.replace_token(request, item["token"], item["token"]), scheme
    else:
        raise ValueError("source.kind is unsupported")
    if not items:
        raise ValueError("no JWT was found in the supplied source")
    if len(items) > MAX_BATCH_ITEMS:
        raise ValueError("source contains more than 100 JWTs")
    return {"items": items}


def _retry(project_id: str, old_job_id: str, meta: dict[str, Any], tool: str, store: Store) -> dict[str, Any]:
    job = store.job(project_id, old_job_id)
    if job["status"] != "error":
        raise ValueError("only a failed job can be retried")
    profile, source = store.source(project_id, old_job_id)
    source["retry_of"] = old_job_id
    settings = _settings(meta, tool)
    new_id = store.create_job(project_id, profile, source)
    action = lambda: engine.run_job(new_id, source, settings, store, lambda: store.cancelled(new_id))
    RUNNER.submit(new_id, action, _bounded(settings.get("max_concurrent_jobs", 2), 1, 8, "max_concurrent_jobs"))
    store.event(new_id, "retry", "queued", "Explicit retry of failed job " + old_job_id)
    return {"job_id": new_id, "retry_of": old_job_id, "status": "queued"}


def _settings(meta: dict[str, Any], tool: str) -> dict[str, Any]:
    result = host_call("xsec.jwt-analysis.settings_get", {"tool": tool}, meta)
    return merge_settings(result.get("settings", {}))


def host_call(method: str, params: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    endpoint = os.environ.get("XSEC_PLUGIN_HOST_RPC_ENDPOINT", "")
    handle = meta.get(CONTEXT_KEY)
    if not endpoint or not isinstance(handle, str) or not handle:
        raise PermissionError("trusted Desktop Host context is unavailable")
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path != "/plugin-host-rpc":
        raise PermissionError("Desktop Host RPC endpoint is invalid")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(endpoint, body, {"Authorization": "Bearer " + handle,
                                                       "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read(1024 * 1024))
    if "error" in value:
        raise PermissionError(value["error"].get("message", "Desktop Host rejected the request"))
    return value["result"]


def _request_value(value: Any, scheme_value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        _check_scheme(scheme_value)
        return None, scheme_value
    if isinstance(value, str):
        _check_scheme(scheme_value)
        return value, scheme_value
    if isinstance(value, dict) and isinstance(value.get("raw"), str):
        selected = value.get("scheme", scheme_value)
        _check_scheme(selected)
        return value["raw"], selected
    raise ValueError("request must be a raw HTTP request string or {raw, scheme}")


def _check_scheme(value: Any) -> None:
    if value not in (None, "http", "https"):
        raise ValueError("scheme must be http or https")


def _validate_items(items: list[dict[str, Any]]) -> None:
    unique = []
    seen = set()
    for item in items:
        item["fingerprint"] = jwt.fingerprint(item["token"])
        key = (item["fingerprint"], item.get("request"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    items[:] = unique


def _required_string(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _bounded(value: Any, minimum: int, maximum: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _limit(value: Any, default: int) -> int:
    if value is None:
        return default
    return _bounded(value, 0 if default == 0 else 1, MAX_LIST_LIMIT, "limit")


def _rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _store() -> Store:
    data = os.environ.get("PLUGIN_DATA")
    if not data:
        raise RuntimeError("PLUGIN_DATA was not provided by XSEC Desktop")
    return Store(data)


RUNNER = JobRunner(record_failure)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
