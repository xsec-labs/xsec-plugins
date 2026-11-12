from __future__ import annotations

import hashlib
import os
import tarfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from . import jwt
from .jwt_tool_adapter import UPSTREAM_VERSION, verify_key
from .probe import run_active
from .results import nday_catalog, result as _result
from .store import Store


def run_job(job_id: str, source: dict[str, Any], settings: dict[str, Any], store: Store,
            cancelled: Callable[[], bool]) -> None:
    store.status(job_id, "running", "parse")
    for item in source["items"]:
        if cancelled():
            store.status(job_id, "cancelled", "cancelled")
            return
        try:
            parsed = jwt.parse(item["token"])
        except ValueError as error:
            parsed = {"fingerprint": jwt.fingerprint(item["token"]), "header": {}, "payload": {},
                      "signature": "", "signing_input": b""}
            store.token(job_id, item["token"], parsed)
            _result(store, job_id, parsed, "structure", "static", None, "error", {"reason": str(error)})
            store.status(job_id, "error")
            store.event(job_id, "parse", "error", str(error))
            return
        store.token(job_id, item["token"], parsed)
        _add_static_results(job_id, item, parsed, store)
        secret = _find_secret(job_id, item["token"], parsed, settings, store, cancelled)
        if cancelled():
            store.status(job_id, "cancelled", "cancelled")
            return
        if source["profile"] == "full":
            run_active(job_id, item, parsed, secret, settings, source, store, cancelled)
            if cancelled():
                store.status(job_id, "cancelled", "cancelled")
                return
    store.status(job_id, "completed", "completed")


def _add_static_results(job_id: str, item: dict[str, Any], parsed: dict[str, Any], store: Store) -> None:
    payload = parsed["payload"]
    now = int(time.time())
    time_claims = {key: payload.get(key) for key in ("iat", "nbf", "exp", "jti") if key in payload}
    time_status = "candidate" if any(key in payload for key in ("iat", "nbf", "exp")) else "not_applicable"
    issued = payload.get("iat")
    expiry = payload.get("exp")
    not_before = payload.get("nbf")
    numeric = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
    details = {"header": parsed["header"], "claims": time_claims,
               "expired": numeric(expiry) and expiry < now,
               "not_yet_valid": numeric(not_before) and not_before > now,
               "issued_age_seconds": now - issued if numeric(issued) else None,
               "validity_seconds": expiry - issued if numeric(issued) and numeric(expiry) else None,
               "exp_drift_seconds": expiry - now if numeric(expiry) else None,
               "nbf_drift_seconds": not_before - now if numeric(not_before) else None,
               "source": item.get("source", "token")}
    _result(store, job_id, parsed, "structure", "static", None, "not_vulnerable", details)
    _result(store, job_id, parsed, "timestamps", "claims", None, time_status, details)
    for test_id, cve, applicable, reason in nday_catalog(parsed["header"]):
        status = "not_run" if applicable else "not_applicable"
        _result(store, job_id, parsed, test_id, "nday", cve, status,
                {"reason": reason, "upstream": "jwt_tool " + UPSTREAM_VERSION})


def _wordlist_paths(settings: dict[str, Any], plugin_root: Path) -> list[tuple[str, Path]]:
    wordlists = settings.get("wordlists", ["jwt-common", "rockyou", "custom"])
    paths = []
    if "jwt-common" in wordlists:
        paths.append(("jwt-common", plugin_root / "wordlists" / "jwt-common.txt"))
    if "rockyou" in wordlists and settings.get("rockyou_enabled", True):
        paths.append(("rockyou", plugin_root / "wordlists" / "rockyou.txt.tar.gz"))
    if "custom" in wordlists:
        for path in settings.get("custom_wordlists", []):
            paths.append(("custom:" + hashlib.sha256(path.encode()).hexdigest()[:12], Path(path)))
    return paths


def _find_secret(job_id: str, token: str, parsed: dict[str, Any], settings: dict[str, Any],
                 store: Store, cancelled: Callable[[], bool]) -> bytes | None:
    if parsed["header"].get("alg") not in ("HS256", "HS384", "HS512"):
        _result(store, job_id, parsed, "weak-secret", "secret", None, "not_applicable",
                {"reason": "jwt_tool supports dictionary verification for HS256, HS384 and HS512"})
        return None
    if verify_key(b"", parsed):
        _save_key_hit(job_id, token, parsed, "empty-key", b"", 1, 0, store)
        store.wordlist_run(job_id, parsed["fingerprint"], "empty-key", 1, True)
        return b""
    total_candidates = 0
    total_invalid_utf8 = 0
    for name, path in _wordlist_paths(settings, Path(os.environ["PLUGIN_ROOT"])):
        matched = False
        count = 0
        invalid_utf8 = 0
        for candidate in _read_wordlist(name, path):
            if cancelled():
                return None
            try:
                candidate.decode("utf-8")
            except UnicodeDecodeError:
                if name != "rockyou":
                    raise
                invalid_utf8 += 1
                total_invalid_utf8 += 1
                continue
            count += 1
            total_candidates += 1
            if verify_key(candidate, parsed):
                matched = True
                _save_key_hit(job_id, token, parsed, name, candidate, count, invalid_utf8, store)
                store.wordlist_run(job_id, parsed["fingerprint"], name, count, True, invalid_utf8)
                return candidate
        store.wordlist_run(job_id, parsed["fingerprint"], name, count, matched, invalid_utf8)
    _result(store, job_id, parsed, "weak-secret", "secret", None, "not_vulnerable",
            {"reason": "no candidate matched", "candidates_tested": total_candidates,
             "invalid_utf8_skipped": total_invalid_utf8})
    return None


def _read_wordlist(name: str, path: Path) -> Iterator[bytes]:
    if not path.is_file():
        raise FileNotFoundError(f"configured JWT wordlist is unavailable: {name}")
    if name == "rockyou":
        with tarfile.open(path, mode="r|gz") as archive:
            member = next((item for item in archive if item.name.endswith("rockyou.txt")), None)
            if member is None or not member.isfile():
                raise ValueError("RockYou archive does not contain a regular rockyou.txt file")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("RockYou archive entry cannot be read")
            for line in stream:
                yield line.rstrip(b"\r\n")
        return
    with path.open("rb") as stream:
        for line in stream:
            candidate = line.rstrip(b"\r\n")
            if name.startswith("custom:"):
                candidate.decode("utf-8")
            yield candidate


def _save_key_hit(job_id: str, token: str, parsed: dict[str, Any], name: str,
                  candidate: bytes, count: int, invalid_utf8: int, store: Store) -> None:
    secret = candidate.decode("utf-8", errors="replace")
    details = {"matched_wordlist": name, "key_length": len(candidate),
               "key_masked": _mask(secret), "candidates_tested": count,
               "invalid_utf8_skipped": invalid_utf8}
    evidence_id = store.evidence(job_id, "weak-secret", {**details, "secret": secret,
                                 "token": token, "tool_version": UPSTREAM_VERSION})
    _result(store, job_id, parsed, "weak-secret", "secret", None, "vulnerable", details, evidence_id)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "•" * len(value)
    return value[:2] + "•" * min(12, len(value) - 4) + value[-2:]
