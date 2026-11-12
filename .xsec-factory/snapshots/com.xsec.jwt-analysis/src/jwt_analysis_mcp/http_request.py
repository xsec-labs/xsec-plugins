from __future__ import annotations

import hashlib
import http.client
import ssl
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit


MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_REQUESTS_PER_JOB = 100
RATE_PERIOD_SECONDS = 60
MAX_REDIRECTS = 3
CANCEL_POLL_SECONDS = 0.25


class RequestLimiter:
    def __init__(self, settings: dict[str, Any], cancelled: Callable[[], bool] = lambda: False) -> None:
        rate = max(1, min(60, int(settings.get("rate_limit", 10))))
        self.interval = RATE_PERIOD_SECONDS / rate
        self.maximum = max(1, min(MAX_REQUESTS_PER_JOB, int(settings.get("max_requests_per_job", MAX_REQUESTS_PER_JOB))))
        self.requests = 0
        self.cancelled = cancelled

    @property
    def exhausted(self) -> bool:
        return self.requests >= self.maximum

    def wait(self) -> None:
        if self.cancelled():
            raise InterruptedError("active request cancelled")
        if self.exhausted:
            raise ValueError("per-job active HTTP request limit reached")
        if self.requests:
            deadline = time.monotonic() + self.interval
            while True:
                if self.cancelled():
                    raise InterruptedError("active request cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(CANCEL_POLL_SECONDS, remaining))
        self.requests += 1


class RawHttp:
    def __init__(self, settings: dict[str, Any], limiter: RequestLimiter) -> None:
        self.settings = settings
        self.limiter = limiter

    def send(self, raw: str, scheme: str | None) -> dict[str, Any]:
        request = parse_request(raw, scheme)
        response = self._once(request)
        return self._follow(request, response, request["origin"], 0)

    def _follow(self, request: dict[str, Any], response: dict[str, Any],
                origin: tuple[str, str, int], hops: int) -> dict[str, Any]:
        if response["status"] not in (301, 302, 303, 307, 308):
            return response
        policy = self.settings.get("redirect_policy", "disabled")
        if policy == "disabled":
            return response
        if policy != "same-origin":
            raise ValueError("redirect_policy must be disabled or same-origin")
        if hops >= MAX_REDIRECTS:
            raise ValueError("same-origin redirect limit reached")
        location = _header(response["headers"], "location")
        if not location:
            return response
        target = urlsplit(urljoin(request["url"], location))
        if _origin(target.scheme, target.netloc) != origin:
            raise ValueError("cross-origin redirect was blocked")
        redirected = _redirect_request(request, target)
        return self._follow(redirected, self._once(redirected), origin, hops + 1)

    def _once(self, request: dict[str, Any]) -> dict[str, Any]:
        self.limiter.wait()
        connection = _connection(request, self.settings)
        started = time.monotonic()
        try:
            _write_request(connection, request)
            response = connection.getresponse()
            raw_body = response.read(MAX_RESPONSE_BYTES + 1)
            truncated = len(raw_body) > MAX_RESPONSE_BYTES
            body = raw_body[:MAX_RESPONSE_BYTES]
            return {"status": response.status, "reason": response.reason,
                    "headers": response.getheaders(), "body": body.decode("utf-8", errors="replace"),
                    "body_sha256": hashlib.sha256(body).hexdigest(), "truncated": truncated,
                    "length": len(body), "duration_ms": round((time.monotonic() - started) * 1000)}
        finally:
            connection.close()


def parse_request(raw: str, scheme: str | None) -> dict[str, Any]:
    if len(raw.encode()) > MAX_REQUEST_BYTES:
        raise ValueError("baseline request exceeds the 2 MiB limit")
    lines = raw.split("\r\n")
    first = lines[0].split(" ")
    if len(first) != 3 or not first[2].startswith("HTTP/1."):
        raise ValueError("baseline must be a raw HTTP/1.x request")
    separator = next((index for index, line in enumerate(lines) if not line), None)
    if separator is None:
        raise ValueError("baseline request is missing its CRLF header terminator")
    headers = [_header_pair(line) for line in lines[1:separator]]
    host = next((value for name, value in headers if name.lower() == "host"), "")
    target = urlsplit(first[1])
    selected_scheme, host = target.scheme or scheme, target.netloc or host
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    host_url = urlsplit("//" + host)
    if selected_scheme not in ("http", "https") or not host_url.hostname or host_url.username or host_url.password:
        raise ValueError("baseline needs a valid Host and explicit http/https scheme")
    if not path.startswith("/"):
        raise ValueError("baseline request target must use origin form or an absolute URL")
    port = host_url.port or (443 if selected_scheme == "https" else 80)
    return {"method": first[0], "path": path, "headers": headers,
            "body": "\r\n".join(lines[separator + 1:]).encode(),
            "scheme": selected_scheme, "host": host, "hostname": host_url.hostname,
            "port": port, "origin": _origin(selected_scheme, host),
            "url": f"{selected_scheme}://{host}{path}"}


def _header_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError("baseline contains an invalid HTTP header")
    name, value = line.split(":", 1)
    if not name or any(ord(char) < 33 or ord(char) > 126 for char in name) or "\r" in value or "\n" in value:
        raise ValueError("baseline contains an invalid HTTP header")
    return name, value.strip()


def _origin(scheme: str, host: str) -> tuple[str, str, int]:
    parsed = urlsplit("//" + host)
    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, (parsed.hostname or "").lower(), port


def _connection(request: dict[str, Any], settings: dict[str, Any]) -> http.client.HTTPConnection:
    timeout = int(settings.get("request_timeout_seconds", 10))
    if request["scheme"] == "https":
        context = ssl.create_default_context() if settings.get("tls_verify", True) else ssl._create_unverified_context()
        return http.client.HTTPSConnection(request["hostname"], request["port"], timeout=timeout, context=context)
    return http.client.HTTPConnection(request["hostname"], request["port"], timeout=timeout)


def _write_request(connection: http.client.HTTPConnection, request: dict[str, Any]) -> None:
    connection.putrequest(request["method"], request["path"], skip_host=True, skip_accept_encoding=True)
    skipped = {"host", "connection", "content-length", "transfer-encoding", "keep-alive", "upgrade"}
    for name, value in request["headers"]:
        if name.lower() not in skipped:
            connection.putheader(name, value)
    if request["body"]:
        connection.putheader("Content-Length", str(len(request["body"])))
    connection.putheader("Host", request["host"])
    connection.putheader("Connection", "close")
    connection.endheaders(request["body"] if request["body"] else None)


def _redirect_request(old: dict[str, Any], target: Any) -> dict[str, Any]:
    host = target.netloc
    port = target.port or (443 if target.scheme == "https" else 80)
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    return {**old, "scheme": target.scheme, "host": host, "hostname": target.hostname,
            "port": port, "path": path, "url": target.geturl(), "origin": _origin(target.scheme, host)}


def _header(headers: list[tuple[str, str]], name: str) -> str:
    return next((value for key, value in headers if key.lower() == name), "")
