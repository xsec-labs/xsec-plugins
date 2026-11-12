from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any


TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*")
MAX_TOKEN_BYTES = 64 * 1024


def _decode_segment(segment: str, label: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"JWT {label} is not valid base64url") from error


def parse(token: str) -> dict[str, Any]:
    if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise ValueError("JWT exceeds the 64 KiB analysis limit")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("JWT must contain exactly three segments")
    header = json.loads(_decode_segment(parts[0], "header"))
    payload = json.loads(_decode_segment(parts[1], "payload")) if parts[1] else {}
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("JWT header and payload must be JSON objects")
    return {
        "header": header,
        "payload": payload,
        "signature": parts[2],
        "signing_input": (parts[0] + "." + parts[1]).encode("ascii"),
        "fingerprint": fingerprint(token),
    }


def fingerprint(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode()).hexdigest()


def encode_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def replace_token(raw_request: str, old: str, new: str) -> str:
    if old in raw_request:
        return raw_request.replace(old, new)
    tokens = extract_tokens(raw_request)
    if tokens:
        return raw_request.replace(tokens[0], new)
    lines = raw_request.split("\r\n")
    end = next((index for index, line in enumerate(lines) if not line), None)
    if end is None:
        raise ValueError("baseline request has no header terminator")
    lines.insert(end, "Authorization: Bearer " + new)
    return "\r\n".join(lines)


def extract_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_RE.findall(text)))
