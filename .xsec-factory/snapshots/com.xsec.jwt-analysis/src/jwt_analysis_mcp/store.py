from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import sqlite3
import uuid
import re
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
  profile TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT,
  finished_at TEXT, cancelled INTEGER NOT NULL DEFAULT 0, source_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jwt_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT, token_fingerprint TEXT NOT NULL,
  job_id TEXT NOT NULL REFERENCES jobs(job_id),
  token TEXT NOT NULL, header_json TEXT NOT NULL, payload_json TEXT NOT NULL,
  algorithm TEXT, key_id TEXT, UNIQUE(job_id, token_fingerprint)
);
CREATE TABLE IF NOT EXISTS test_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  token_fingerprint TEXT NOT NULL, test_id TEXT NOT NULL, category TEXT NOT NULL,
  cve TEXT, status TEXT NOT NULL, severity TEXT NOT NULL, confidence TEXT NOT NULL,
  details_json TEXT NOT NULL, evidence_id TEXT,
  UNIQUE(job_id, token_fingerprint, test_id)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  test_id TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  stage TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wordlist_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  token_fingerprint TEXT NOT NULL, wordlist_id TEXT NOT NULL,
  candidates INTEGER NOT NULL, matched INTEGER NOT NULL, invalid_utf8 INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_jobs_project ON jobs(project_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_job ON events(job_id, sequence);
CREATE INDEX IF NOT EXISTS ix_results_job ON test_results(job_id, id);
"""


class Store:
    def __init__(self, data_dir: str) -> None:
        self.root = Path(data_dir).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.path = self.root / "jwt-analysis.sqlite"
        with self.connection() as db:
            db.executescript(SCHEMA)
        self.path.chmod(0o600)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_job(self, project_id: str, profile: str, source: dict[str, Any]) -> str:
        job_id = "jwt-" + uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO jobs(job_id,project_id,status,profile,created_at,source_json) "
                "VALUES(?,?,'queued',?,?,?)",
                (job_id, project_id, profile, _now(), _json(source)),
            )
        self.event(job_id, "queued", "queued", "Analysis job queued")
        return job_id

    def event(self, job_id: str, stage: str, status: str, message: str) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO events(job_id,stage,status,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, stage, status, message, _now()),
            )

    def status(self, job_id: str, status: str, stage: str | None = None) -> None:
        now = _now()
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET status=?, started_at=COALESCE(started_at,?), "
                "finished_at=CASE WHEN ? IN ('completed','error','cancelled') THEN ? ELSE finished_at END "
                "WHERE job_id=?",
                (status, now, status, now, job_id),
            )
        if stage:
            self.event(job_id, stage, status, stage.replace("_", " "))

    def token(self, job_id: str, token: str, parsed: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO jwt_tokens(token_fingerprint,job_id,token,header_json,payload_json,algorithm,key_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (parsed["fingerprint"], job_id, token, _json(parsed["header"]),
                 _json(parsed["payload"]), parsed["header"].get("alg"),
                 parsed["header"].get("kid")),
            )

    def result(self, job_id: str, fingerprint: str, value: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO test_results(job_id,token_fingerprint,test_id,category,cve,status,"
                "severity,confidence,details_json,evidence_id) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(job_id,token_fingerprint,test_id) DO UPDATE SET "
                "category=excluded.category,cve=excluded.cve,status=excluded.status,"
                "severity=excluded.severity,confidence=excluded.confidence,"
                "details_json=excluded.details_json,evidence_id=excluded.evidence_id",
                (job_id, fingerprint, value["test_id"], value["category"], value.get("cve"),
                 value["status"], value.get("severity", "informational"),
                 value.get("confidence", "low"), _json(value.get("details", {})),
                 value.get("evidence_id")),
            )

    def evidence(self, job_id: str, test_id: str, value: dict[str, Any]) -> str:
        evidence_id = "ev-" + uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO evidence VALUES(?,?,?,?)",
                (evidence_id, job_id, test_id, _json(value)),
            )
        return evidence_id

    def wordlist_run(self, job_id: str, fingerprint: str, name: str, count: int,
                     matched: bool, invalid_utf8: int = 0) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO wordlist_runs(job_id,token_fingerprint,wordlist_id,candidates,matched,invalid_utf8) "
                "VALUES(?,?,?,?,?,?)", (job_id, fingerprint, name, count, int(matched), invalid_utf8),
            )

    def cancelled(self, job_id: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT cancelled FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return bool(row[0]) if row else True

    def cancel(self, project_id: str, job_id: str) -> bool:
        now = _now()
        with self.connection() as db:
            cursor = db.execute(
                "UPDATE jobs SET cancelled=1, status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END, "
                "finished_at=CASE WHEN status='queued' THEN ? ELSE finished_at END "
                "WHERE job_id=? AND project_id=? "
                "AND status IN ('queued','running')", (now, job_id, project_id),
            )
        changed = cursor.rowcount == 1
        if changed:
            self.event(job_id, "cancelled", "requested", "Explicit cancellation requested")
        return changed

    def recover_interrupted(self) -> None:
        with self.connection() as db:
            rows = db.execute("SELECT job_id FROM jobs WHERE status IN ('queued','running')").fetchall()
            now = _now()
            db.execute("UPDATE jobs SET status='error',finished_at=? WHERE status IN ('queued','running')", (now,))
        for row in rows:
            self.event(row["job_id"], "error", "error", "Sidecar stopped before completion; explicit retry is required")

    def job(self, project_id: str, job_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=? AND project_id=?", (job_id, project_id)).fetchone()
            if row is None:
                raise ValueError("job not found in this project")
            tokens = db.execute("SELECT * FROM jwt_tokens WHERE job_id=?", (job_id,)).fetchall()
            results = db.execute("SELECT * FROM test_results WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
            wordlists = db.execute("SELECT * FROM wordlist_runs WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
        return _job_view(row, tokens, results, wordlists)

    def source(self, project_id: str, job_id: str) -> tuple[str, dict[str, Any]]:
        with self.connection() as db:
            row = db.execute(
                "SELECT profile,source_json FROM jobs WHERE job_id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
        if row is None:
            raise ValueError("job not found in this project")
        return row["profile"], json.loads(row["source_json"])

    def delete(self, project_id: str, job_id: str) -> None:
        with self.connection() as db:
            row = db.execute(
                "SELECT status FROM jobs WHERE job_id=? AND project_id=?", (job_id, project_id)
            ).fetchone()
            if row is None:
                raise ValueError("job not found in this project")
            if row["status"] in ("queued", "running"):
                raise ValueError("cancel the running job before deleting it")
            for table in ("events", "test_results", "evidence", "wordlist_runs", "jwt_tokens"):
                db.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
            db.execute("DELETE FROM jobs WHERE job_id=? AND project_id=?", (job_id, project_id))

    def list_jobs(self, project_id: str, limit: int) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [{key: row[key] for key in ("job_id", "status", "profile", "created_at", "started_at", "finished_at")} for row in rows]

    def events(self, project_id: str, job_id: str, cursor: int, limit: int) -> dict[str, Any]:
        self.job(project_id, job_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (job_id, cursor, limit),
            ).fetchall()
        items = [{key: row[key] for key in ("sequence", "stage", "status", "message", "created_at")} for row in rows]
        return {"items": items, "next_cursor": items[-1]["sequence"] if items else cursor}

    def evidence_get(self, project_id: str, evidence_id: str, reveal: bool,
                     redaction: str = "standard") -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT e.* FROM evidence e JOIN jobs j ON e.job_id=j.job_id "
                "WHERE e.evidence_id=? AND j.project_id=?", (evidence_id, project_id),
            ).fetchone()
        if row is None:
            raise ValueError("evidence not found in this project")
        evidence = json.loads(row["evidence_json"])
        if redaction not in ("standard", "strict", "none"):
            raise ValueError("evidence redaction must be standard, strict or none")
        if not reveal and redaction != "none":
            evidence = _redact(evidence, redaction)
        return {"evidence_id": evidence_id, "job_id": row["job_id"], "test_id": row["test_id"], "evidence": evidence}


def _job_view(row: sqlite3.Row, tokens: list[sqlite3.Row], results: list[sqlite3.Row],
              wordlists: list[sqlite3.Row]) -> dict[str, Any]:
    tests = [{"token_fingerprint": item["token_fingerprint"], "test_id": item["test_id"], "category": item["category"], "cve": item["cve"],
              "status": item["status"], "severity": item["severity"], "confidence": item["confidence"],
              "details": json.loads(item["details_json"]), "evidence_id": item["evidence_id"]} for item in results]
    token_views = [{"token_fingerprint": item["token_fingerprint"], "header": json.loads(item["header_json"]),
                    "payload": json.loads(item["payload_json"]), "signature": _signature(item["token"]),
                    "algorithm": item["algorithm"], "key_id": item["key_id"]} for item in tokens]
    return {"job_id": row["job_id"], "project_id": row["project_id"], "status": row["status"],
            "profile": row["profile"], "created_at": row["created_at"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "tokens": token_views, "tests": tests,
            "wordlist_runs": [{key: item[key] for key in ("token_fingerprint", "wordlist_id", "candidates", "matched", "invalid_utf8")}
                              for item in wordlists]}


def _signature(token: str) -> str:
    parts = token.split(".")
    return parts[2] if len(parts) == 3 else ""


def _redact(value: Any, mode: str) -> Any:
    if isinstance(value, dict):
        sensitive = {"token", "variant_token", "secret", "authorization", "proxy-authorization",
                     "cookie", "set-cookie", "password", "client_secret"}
        if mode == "strict":
            sensitive |= {"body", "request"}
        return {key: ("[REDACTED]" if _sensitive_key(key.lower(), sensitive) else _redact(item, mode))
                for key, item in value.items()}
    if isinstance(value, list):
        if len(value) == 2 and isinstance(value[0], str) and value[0].lower() in (
            "authorization", "proxy-authorization", "cookie", "set-cookie"
        ):
            return [value[0], "[REDACTED]"]
        return [_redact(item, mode) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?im)^(authorization|proxy-authorization|cookie|set-cookie)\s*:[^\r\n]*",
                       r"\1: [REDACTED]", value)
        value = re.sub(r"(?i)(access_token|refresh_token|id_token|client_secret|password)=([^&\s;]+)",
                       r"\1=[REDACTED]", value)
        value = re.sub(r'(?i)("(?:access_token|refresh_token|id_token|client_secret|password)"\s*:\s*")[^\"]*',
                       r"\1[REDACTED]", value)
        return re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*",
                      "[JWT REDACTED]", value)
    return value


def _sensitive_key(key: str, exact: set[str]) -> bool:
    return key in exact or (key.endswith("_token") and "fingerprint" not in key)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
