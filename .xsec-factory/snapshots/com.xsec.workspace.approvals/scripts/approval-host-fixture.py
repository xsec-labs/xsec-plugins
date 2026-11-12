"""Seed/remove approval records in an explicitly selected temporary Debug database."""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

PREFIX = "approval-plugin-regression-"
COUNT = 85
LONG_REPEATS = 12_000
SUFFIX = "完整详情结束"


def seed(connection):
    timestamp = int(time.time() * 1000)
    rows = []
    for index in range(COUNT):
        request = f"{PREFIX}{index:03}"
        arguments = "中文审批🦀" * LONG_REPEATS + SUFFIX if index == COUNT - 1 else "{}"
        rows.append((request, request, PREFIX + "session", "manual", f"tool-{index:03}",
                     "allowed" if index % 2 == 0 else "denied", arguments, timestamp, timestamp))
    rows.append((PREFIX + "foreign", PREFIX + "foreign", PREFIX + "other", "manual",
                 "other-tool", "denied", "{}", timestamp, timestamp))
    connection.executemany("""INSERT INTO approval_events
        (id, request_id, session_id, mode, tool_name, decision, arguments_preview, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
    return {"sessionId": PREFIX + "session", "otherSessionId": PREFIX + "other", "expectedCount": COUNT,
            "longRequestId": PREFIX + f"{COUNT - 1:03}", "expectedArgumentSuffix": SUFFIX,
            "toolName": "tool-083", "foreignRequestId": PREFIX + "foreign"}


def main():
    action, database = sys.argv[1:]
    path = Path(database).resolve(strict=True)
    temp_roots = (Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve())
    if not any(path.is_relative_to(root) for root in temp_roots):
        raise ValueError("Use a disposable XSEC_DEBUG_DATA_ROOT under the OS temporary directory")
    with sqlite3.connect(f"file:{path}?mode=rw", uri=True) as connection:
        if action == "seed":
            result = seed(connection)
            print(json.dumps(result, ensure_ascii=False))
        elif action == "remove":
            connection.execute("DELETE FROM approval_events WHERE session_id IN (?, ?)",
                               (PREFIX + "session", PREFIX + "other"))
        else:
            raise ValueError("Expected seed or remove")


if __name__ == "__main__":
    main()
