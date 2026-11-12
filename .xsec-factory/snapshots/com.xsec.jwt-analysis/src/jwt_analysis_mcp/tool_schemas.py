from __future__ import annotations

from typing import Any


MAX_LIST_LIMIT = 200


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return {"name": name, "description": description, "inputSchema": schema}


TOOLS = [
    _tool("jwt_analysis_diagnostics", "Check the bundled Sidecar and jwt_tool runtime.", {}),
    _tool("jwt_analysis_create", "Create a persistent JWT analysis job.", {
        "source": {"type": "object", "properties": {"kind": {"enum": ["token", "traffic_ref", "request_file", "project_file", "batch"]},
            "token": {"type": "string"}, "flow_id": {"type": "string"}, "path": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}}}, "required": ["kind"]},
        "profile": {"enum": ["full", "passive"]},
        "wordlists": {"type": "array", "items": {"enum": ["jwt-common", "rockyou", "custom"]}},
        "custom_wordlists": {"type": "array", "items": {"type": "string"}},
        "request": {"type": ["string", "object"], "description": "Explicit authorized HTTP/1.x baseline request."},
        "scheme": {"enum": ["http", "https"]}, "canary": {"type": "string"},
        "rate_limit": {"type": "integer", "minimum": 1, "maximum": 60},
    }, ["source"]),
    _tool("jwt_analysis_list", "List JWT analysis jobs in the bound project.", {"limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIST_LIMIT}}),
    _tool("jwt_analysis_get", "Get parsed JWT claims and job test results.", {"job_id": {"type": "string"}}, ["job_id"]),
    _tool("jwt_analysis_events", "Read job progress events after a cursor.", {"job_id": {"type": "string"}, "cursor": {"type": "integer", "minimum": 0}}, ["job_id"]),
    _tool("jwt_analysis_cancel", "Explicitly cancel a queued or running job.", {"job_id": {"type": "string"}}, ["job_id"]),
    _tool("jwt_analysis_retry", "Explicitly rerun a failed job from its saved input.", {"job_id": {"type": "string"}}, ["job_id"]),
    _tool("jwt_analysis_evidence_get", "Read evidence; secrets are redacted unless explicitly requested.", {"evidence_id": {"type": "string"}, "include_sensitive": {"type": "boolean"}}, ["evidence_id"]),
    _tool("jwt_analysis_report", "Generate a Markdown or JSON report without raw tokens.", {"job_id": {"type": "string"}, "format": {"enum": ["markdown", "json"]}}, ["job_id"]),
    _tool("jwt_analysis_delete", "Permanently delete a completed or failed job and its evidence.", {"job_id": {"type": "string"}}, ["job_id"]),
]
