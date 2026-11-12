from __future__ import annotations

from typing import Any


DEFAULTS = {
    "wordlists": ["jwt-common", "rockyou", "custom"],
    "rockyou_enabled": True,
    "custom_wordlists": [],
    "max_concurrent_jobs": 2,
    "max_requests_per_job": 100,
    "rate_limit": 10,
    "request_timeout_seconds": 10,
    "redirect_policy": "disabled",
    "tls_verify": True,
    "evidence_redaction": "standard",
    "retention": "permanent",
    "jwks_allowlist": [],
    "listener_enabled": False,
    "public_key": "",
}


def merge(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("JWT analysis settings are invalid")
    settings = {**DEFAULTS, **value}
    _string_list(settings, "wordlists", ("jwt-common", "rockyou", "custom"))
    _string_list(settings, "custom_wordlists")
    _string_list(settings, "jwks_allowlist")
    _integer(settings, "max_concurrent_jobs", 1, 8)
    _integer(settings, "max_requests_per_job", 1, 100)
    _integer(settings, "rate_limit", 1, 60)
    _integer(settings, "request_timeout_seconds", 1, 60)
    _boolean(settings, "rockyou_enabled")
    _boolean(settings, "tls_verify")
    _boolean(settings, "listener_enabled")
    if settings["redirect_policy"] not in ("disabled", "same-origin"):
        raise ValueError("redirect_policy must be disabled or same-origin")
    if settings["evidence_redaction"] not in ("strict", "standard", "none"):
        raise ValueError("evidence_redaction must be strict, standard or none")
    if settings["retention"] != "permanent":
        raise ValueError("JWT analysis retention must be permanent")
    if settings["listener_enabled"] or settings["jwks_allowlist"]:
        raise ValueError("external JWKS listeners are not available in this Sidecar")
    if not isinstance(settings["public_key"], str) or len(settings["public_key"]) > 65536:
        raise ValueError("public_key must be PEM text no larger than 64 KiB")
    return settings


def _string_list(settings: dict[str, Any], key: str, allowed: tuple[str, ...] = ()) -> None:
    values = settings[key]
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{key} must be an array of strings")
    if allowed and any(value not in allowed for value in values):
        raise ValueError(f"{key} contains an unsupported value")


def _integer(settings: dict[str, Any], key: str, minimum: int, maximum: int) -> None:
    value = settings[key]
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be an integer from {minimum} to {maximum}")


def _boolean(settings: dict[str, Any], key: str) -> None:
    if not isinstance(settings[key], bool):
        raise ValueError(f"{key} must be a boolean")
