from __future__ import annotations

from typing import Any

from .store import Store


UPSTREAM_VERSION = "2.3.0"


def nday_catalog(header: dict[str, Any]) -> list[tuple[str, str | None, bool, str]]:
    alg = str(header.get("alg", ""))
    hmac_algorithm = alg in ("HS256", "HS384", "HS512")
    asymmetric = alg.startswith(("RS", "PS", "ES"))
    return [
        ("alg-none", "CVE-2015-2951", True, "alg=none acceptance test"),
        ("alg-none-titlecase", "CVE-2015-2951", True, "case-variant alg=none acceptance test"),
        ("alg-none-uppercase", "CVE-2015-2951", True, "case-variant alg=none acceptance test"),
        ("alg-none-mixedcase", "CVE-2015-2951", True, "case-variant alg=none acceptance test"),
        ("rs-hs-confusion", "CVE-2016-10555", asymmetric,
         "requires an asymmetric public key" if asymmetric else "requires an asymmetric signing algorithm"),
        ("jwks-injection", "CVE-2018-0114", True,
         "requires an enabled JWKS listener and target allowlist"),
        ("blank-password", "CVE-2019-20933", hmac_algorithm, "requires supported HMAC signing"),
        ("blank-password-2", "CVE-2020-28637", hmac_algorithm, "requires supported HMAC signing"),
        ("null-signature", "CVE-2020-28042", True, "empty signature acceptance test"),
        ("ecdsa-psychic-signature", "CVE-2022-21449", alg.startswith("ES"), "requires ECDSA signing"),
        ("claim-fuzz", None, hmac_algorithm, "valid mutation requires a verified signing key"),
        ("claim-error", None, hmac_algorithm, "requires a verified signing key"),
        ("common-claims", None, True, "requires a verified signing key"),
        ("header-kid", None, True, "kid mutation with the original signature"),
        ("header-jwk", "CVE-2018-0114", True, "embedded jwk mutation with the original signature"),
    ]


def result(store: Store, job_id: str, parsed: dict[str, Any], test_id: str, category: str,
           cve: str | None, status: str, details: dict[str, Any], evidence_id: str | None = None) -> None:
    severity = "high" if status == "vulnerable" else "informational"
    confidence = "confirmed" if status == "vulnerable" else "low"
    store.result(job_id, parsed["fingerprint"], {
        "test_id": test_id, "category": category, "cve": cve, "status": status,
        "severity": severity, "confidence": confidence, "details": details,
        "evidence_id": evidence_id,
    })
