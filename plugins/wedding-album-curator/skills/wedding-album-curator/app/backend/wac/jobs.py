"""Background job execution with progress, pause/resume and cancellation.

One worker thread per project runs jobs sequentially. Job state is persisted in the
project database, so the UI survives page reloads and a restarted app knows which
jobs were interrupted (they can simply be started again; work is incremental).
"""
from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional

from .db import ProjectDB


class Cancelled(Exception):
    pass


@dataclass
class JobContext:
    job_id: int
    db: ProjectDB
    params: dict
    _pause: threading.Event = field(default_factory=threading.Event)
    _cancel: threading.Event = field(default_factory=threading.Event)
    _last_write: float = 0.0
    stage: str = ""
    done: int = 0
    total: int = 0
    message: str = ""

    def check(self) -> None:
        """Call frequently. Blocks while paused; raises Cancelled when cancelled."""
        if self._cancel.is_set():
            raise Cancelled()
        if self._pause.is_set():
            self._write(state="paused")
            while self._pause.is_set():
                if self._cancel.is_set():
                    raise Cancelled()
                time.sleep(0.2)
            self._write(state="running")

    def should_stop(self) -> bool:
        return self._cancel.is_set()

    def progress(self, stage: Optional[str] = None, done: Optional[int] = None, total: Optional[int] = None,
                 message: Optional[str] = None, force: bool = False) -> None:
        if stage is not None:
            self.stage = stage
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total
        if message is not None:
            self.message = message
        now = time.time()
        if force or now - self._last_write > 0.5:
            self._write()

    def _write(self, state: Optional[str] = None) -> None:
        self._last_write = time.time()
        with self.db.tx() as con:
            con.execute(
                "UPDATE jobs SET stage=?, done=?, total=?, message=?" + (", state=?" if state else "") + " WHERE id=?",
                (self.stage, self.done, self.total, self.message, *( [state] if state else []), self.job_id),
            )


JobFn = Callable[[JobContext], Optional[dict]]


class JobManager:
    def __init__(self, db: ProjectDB):
        self.db = db
        self.q: queue.Queue = queue.Queue()
        self.contexts: dict[int, JobContext] = {}
        self.fns: dict[int, JobFn] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        # Anything left "running" from a previous process was interrupted.
        with db.tx() as con:
            con.execute(
                "UPDATE jobs SET state='interrupted', finished_at=? WHERE state IN ('running','queued','paused')",
                (time.time(),),
            )
        self._thread.start()

    def submit(self, kind: str, fn: JobFn, params: Optional[dict] = None) -> int:
        with self.db.connect() as con:
            active = con.execute(
                "SELECT id FROM jobs WHERE kind=? AND state IN ('queued','running','paused')", (kind,)
            ).fetchone()
        if active:
            return active["id"]
        with self.db.tx() as con:
            cur = con.execute(
                "INSERT INTO jobs(kind, state, params) VALUES (?, 'queued', ?)", (kind, json.dumps(params or {}))
            )
            jid = cur.lastrowid
        ctx = JobContext(job_id=jid, db=self.db, params=params or {})
        self.contexts[jid] = ctx
        self.fns[jid] = fn
        self.q.put(jid)
        return jid

    def pause(self, jid: int) -> None:
        if jid in self.contexts:
            self.contexts[jid]._pause.set()

    def resume(self, jid: int) -> None:
        if jid in self.contexts:
            self.contexts[jid]._pause.clear()

    def cancel(self, jid: int) -> None:
        ctx = self.contexts.get(jid)
        if ctx:
            ctx._cancel.set()
            ctx._pause.clear()
        with self.db.tx() as con:
            con.execute("UPDATE jobs SET state='cancelled', finished_at=? WHERE id=? AND state='queued'", (time.time(), jid))

    def list(self, limit: int = 20) -> list[dict]:
        with self.db.connect() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]
        for r in rows:
            r["params"] = json.loads(r["params"] or "{}")
            try:
                r["result"] = json.loads(r["error"]) if r["state"] == "done" and r["error"] else None
            except (TypeError, json.JSONDecodeError):
                r["result"] = None
        return rows

    def _run(self) -> None:
        while True:
            jid = self.q.get()
            ctx = self.contexts.get(jid)
            fn = self.fns.get(jid)
            if ctx is None or fn is None:
                continue
            if ctx._cancel.is_set():
                continue
            with self.db.tx() as con:
                con.execute("UPDATE jobs SET state='running', started_at=? WHERE id=?", (time.time(), jid))
            state, err = "done", None
            try:
                result = fn(ctx) or {}
                err = json.dumps(result)  # successful jobs store their result summary in `error` column
            except Cancelled:
                state = "cancelled"
            except Exception as e:  # keep the worker alive whatever happens
                state = "failed"
                err = f"{type(e).__name__}: {e}"
                traceback.print_exc()
            ctx.progress(force=True)
            with self.db.tx() as con:
                con.execute("UPDATE jobs SET state=?, error=?, finished_at=? WHERE id=?", (state, err, time.time(), jid))
            self.contexts.pop(jid, None)
            self.fns.pop(jid, None)
