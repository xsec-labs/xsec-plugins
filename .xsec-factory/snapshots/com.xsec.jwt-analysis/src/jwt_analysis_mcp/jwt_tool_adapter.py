from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any


UPSTREAM_VERSION = "2.3.0"


@cache
def module() -> Any:
    plugin_root = os.environ.get("PLUGIN_ROOT")
    root = Path(plugin_root).resolve() if plugin_root else Path(__file__).resolve().parents[2]
    source = Path(sys._MEIPASS) / "jwt_tool" / "jwt_tool.py" if getattr(sys, "frozen", False) else root / "jwt_tool" / "jwt_tool.py"
    spec = importlib.util.spec_from_file_location("xsec_jwt_tool", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("bundled jwt_tool 2.3.0 source is unavailable")
    tool = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(tool)
    if tool.jwttoolvers != UPSTREAM_VERSION:
        raise RuntimeError("bundled jwt_tool version does not match the tested adapter")
    tool.args = type("Args", (), {"bare": True})()
    return tool


def verify_key(candidate: bytes, parsed: dict[str, Any]) -> bool:
    with contextlib.redirect_stdout(io.StringIO()):
        return bool(module().testKey(candidate, parsed["signature"], parsed["signing_input"],
                                     parsed["header"], True))


def common_claims() -> tuple[str, ...]:
    plugin_root = os.environ.get("PLUGIN_ROOT")
    root = Path(plugin_root).resolve() if plugin_root else Path(__file__).resolve().parents[2]
    path = root / "jwt_tool" / "common-payloads.txt"
    with path.open(encoding="utf-8") as source:
        return tuple(line.strip() for line in source if line.strip())


def diagnostics() -> dict[str, Any]:
    plugin_root = os.environ.get("PLUGIN_ROOT")
    root = Path(plugin_root).resolve() if plugin_root else Path(__file__).resolve().parents[2]
    wordlist = root / "wordlists" / "rockyou.txt.tar.gz"
    return {"jwt_tool_version": UPSTREAM_VERSION, "sidecar": "ready",
            "rockyou_available": wordlist.is_file(),
            "rockyou_archive_bytes": wordlist.stat().st_size if wordlist.is_file() else 0}


def safe_exploits(parsed: dict[str, Any]) -> dict[str, Any]:
    tool = module()
    header = dict(parsed["header"])
    payload = parsed["signing_input"].split(b".", 1)[1].decode("ascii")
    result = {"alg_none": tool.checkAlgNone(dict(header), payload),
              "null_signature": tool.checkNullSig(parsed["signing_input"])}
    if str(header.get("alg", "")).startswith("ES"):
        result["psychic_signature"] = tool.checkPsySig(dict(header), payload)
    if str(header.get("alg", "")).startswith("HS"):
        sizes = {"HS256": 256, "HS384": 384, "HS512": 512}
        bits = sizes.get(str(header["alg"]))
        if bits:
            signature, signing_input = tool.signTokenHS(dict(header), parsed["payload"], "", bits)
            result["blank_password"] = signing_input + "." + signature
    return result
