from __future__ import annotations

import threading
import json
import os
import sys
from typing import Callable

from .store import Store


class JobRunner:
    def __init__(self, on_error: Callable[[str, Exception], None]) -> None:
        self.on_error = on_error
        self.lock = threading.Lock()
        self.pending: list[tuple[str, Callable[[], None]]] = []
        self.active = 0
        self.limit = 2

    def submit(self, job_id: str, action: Callable[[], None], limit: int) -> None:
        with self.lock:
            self.limit = max(1, min(8, limit))
            self.pending.append((job_id, action))
            self._start_ready()

    def cancel_pending(self, job_id: str) -> None:
        with self.lock:
            self.pending = [entry for entry in self.pending if entry[0] != job_id]

    def _start_ready(self) -> None:
        while self.pending and self.active < self.limit:
            job_id, action = self.pending.pop(0)
            self.active += 1
            threading.Thread(target=self._run, args=(job_id, action), daemon=True).start()

    def _run(self, job_id: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as error:
            self.on_error(job_id, error)
        finally:
            with self.lock:
                self.active -= 1
                self._start_ready()


def record_failure(job_id: str, error: Exception) -> None:
    store = Store(os.environ["PLUGIN_DATA"])
    store.status(job_id, "error")
    store.event(job_id, "error", "error", _safe_failure(error))
    print(json.dumps({"event": "job.failed", "jobId": job_id,
                      "errorType": type(error).__name__}), file=sys.stderr, flush=True)


def _safe_failure(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "A configured input file is unavailable. Check the wordlist settings."
    if isinstance(error, UnicodeError):
        return "An input wordlist is not valid UTF-8."
    if isinstance(error, PermissionError):
        return "The Desktop Host denied an operation."
    return "The analysis stage failed: " + type(error).__name__
