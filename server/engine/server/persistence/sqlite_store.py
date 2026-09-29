from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from engine.utils.logger import Logger


@dataclass
class EntityRecord:
    entity_id: str
    entity_type: str
    name: str
    components: Dict[str, Any]
    updated_at: float


class SqliteStore:
    """
    SQLite persistence with an async write queue.

    What it promises, because a store that carries a whole character and world has to:

    * **A queued write is a snapshot.** It is serialised to JSON on the calling thread,
      so it holds the state at the moment it was queued, not whatever the game has
      become by the time the writer gets to it (and the writer never walks a structure
      the game thread is mutating).
    * **A failed write costs one write.** It is counted (`write_failures`,
      `last_write_error`) and logged, and the writer carries on with the next.
    * **Stopping loses nothing.** `stop_async_writer` (and so `close`) writes everything
      that was queued before it returns.
    * **`flush` means landed.** It returns when every queued write has been attempted,
      not merely when the queue is empty, and reports `False` if that does not happen
      in time (including when no writer is running).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        self._lock = threading.Lock()  # the connection
        self._write_queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._closed = False
        self._pending = 0
        self._pending_cond = threading.Condition()  # guards _pending and the failure counters
        self.write_failures = 0
        self.last_write_error = ""
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    components_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS world_cells (
                    cell_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            # The world's changes since it was built from content, one document per
            # key. The caller owns the envelope (which content set and version it
            # belongs to); the store only keeps and returns it.
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS world_state (
                    key TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._conn.commit()

    # -- the writer ----------------------------------------------------------------

    def start_async_writer(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._writer_loop, daemon=True)
        self._worker.start()

    def stop_async_writer(self, timeout_s: float = 10.0) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            self._write_queue.put(None)  # behind everything already queued, so all of it is written first
            worker.join(timeout=timeout_s)
            if worker.is_alive():
                Logger.error("SqliteStore", "the writer did not finish within %.0fs of being stopped" % timeout_s)
                self._running = False
                return
        self._worker = None
        self._running = False
        self._drain_inline()  # a write queued behind the stop, or with no writer at all

    def _writer_loop(self) -> None:
        while self._running:
            task = self._write_queue.get()
            if task is None:
                break
            self._process(task)

    def _drain_inline(self) -> None:
        while True:
            try:
                task = self._write_queue.get_nowait()
            except queue.Empty:
                return
            if task is not None:
                self._process(task)

    def _process(self, task: Dict[str, Any]) -> None:
        try:
            task_type = task.get("task_type", "entity")
            if task_type == "entity":
                self._write_entity_now(task)
            elif task_type == "world_cell":
                self._write_world_cell_now(task)
            elif task_type == "world_state":
                self._write_world_state_now(task)
        except Exception as error:  # a bad write must cost one write, not the writer
            self._record_failure("%s: %s" % (type(error).__name__, error), task)
        finally:
            if task.get("_counted"):
                with self._pending_cond:
                    self._pending = max(0, self._pending - 1)
                    self._pending_cond.notify_all()

    def _record_failure(self, message: str, task: Optional[Dict[str, Any]] = None) -> None:
        with self._pending_cond:
            self.write_failures += 1
            self.last_write_error = message
        subject = ""
        if task:
            subject = " (%s %s)" % (task.get("task_type", "entity"), task.get("entity_id") or task.get("cell_id") or task.get("key") or "")
        Logger.error("SqliteStore", "write failed%s: %s" % (subject, message))

    def _enqueue(self, task: Dict[str, Any]) -> None:
        if self._closed:
            self._record_failure("the store is closed", task)
            return
        task["_counted"] = True
        with self._pending_cond:
            self._pending += 1
        self._write_queue.put(task)

    def flush(self, timeout_s: float = 2.0) -> bool:
        deadline = time.time() + timeout_s
        with self._pending_cond:
            while self._pending > 0:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self._pending_cond.wait(timeout=min(remaining, 0.05))
        return True

    # -- queueing (serialised on the caller's thread) ---------------------------------

    def queue_entity_upsert(self, entity_id: str, entity_type: str, name: str, components: Dict[str, Any]) -> None:
        try:
            components_json = json.dumps(components, default=str)
        except (TypeError, ValueError) as error:
            self._record_failure("entity %s could not be serialised: %s" % (entity_id, error))
            return
        self._enqueue(
            {
                "task_type": "entity",
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": name,
                "components_json": components_json,
                "updated_at": time.time(),
            }
        )

    def queue_world_cell_upsert(self, cell_id: str, state: Dict[str, Any]) -> None:
        try:
            state_json = json.dumps(state, default=str)
        except (TypeError, ValueError) as error:
            self._record_failure("world cell %s could not be serialised: %s" % (cell_id, error))
            return
        self._enqueue(
            {
                "task_type": "world_cell",
                "cell_id": cell_id,
                "state_json": state_json,
                "updated_at": time.time(),
            }
        )

    def queue_world_state(self, key: str, state: Dict[str, Any]) -> None:
        try:
            state_json = json.dumps(state, default=str)
        except (TypeError, ValueError) as error:
            self._record_failure("world state %s could not be serialised: %s" % (key, error))
            return
        self._enqueue(
            {
                "task_type": "world_state",
                "key": key,
                "state_json": state_json,
                "updated_at": time.time(),
            }
        )

    # -- writing ----------------------------------------------------------------------

    def _write_entity_now(self, payload: Dict[str, Any]) -> None:
        components_json = payload.get("components_json")
        if components_json is None:
            components_json = json.dumps(payload.get("components", {}), default=str)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO entities(entity_id, entity_type, name, components_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    name=excluded.name,
                    components_json=excluded.components_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["entity_id"],
                    payload["entity_type"],
                    payload["name"],
                    components_json,
                    payload["updated_at"],
                ),
            )
            self._conn.commit()

    def _write_world_cell_now(self, payload: Dict[str, Any]) -> None:
        state_json = payload.get("state_json")
        if state_json is None:
            state_json = json.dumps(payload.get("state", {}), default=str)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO world_cells(cell_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cell_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["cell_id"],
                    state_json,
                    payload["updated_at"],
                ),
            )
            self._conn.commit()

    def _write_world_state_now(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO world_state(key, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["key"],
                    payload["state_json"],
                    payload["updated_at"],
                ),
            )
            self._conn.commit()

    # -- reading ----------------------------------------------------------------------

    def load_world_cells(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute("SELECT cell_id, state_json FROM world_cells").fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    def load_world_state(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            row = cur.execute("SELECT state_json FROM world_state WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def load_entity(self, entity_id: str) -> Optional[EntityRecord]:
        with self._lock:
            cur = self._conn.cursor()
            row = cur.execute(
                "SELECT entity_id, entity_type, name, components_json, updated_at FROM entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
        if not row:
            return None
        return EntityRecord(
            entity_id=row[0],
            entity_type=row[1],
            name=row[2],
            components=json.loads(row[3]),
            updated_at=row[4],
        )

    def list_entities(self, entity_type: Optional[str] = None) -> List[EntityRecord]:
        with self._lock:
            cur = self._conn.cursor()
            if entity_type:
                rows = cur.execute(
                    "SELECT entity_id, entity_type, name, components_json, updated_at FROM entities WHERE entity_type = ?",
                    (entity_type,),
                ).fetchall()
            else:
                rows = cur.execute(
                    "SELECT entity_id, entity_type, name, components_json, updated_at FROM entities"
                ).fetchall()
        return [
            EntityRecord(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2],
                components=json.loads(row[3]),
                updated_at=row[4],
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._closed:
            return
        self.stop_async_writer()  # writes whatever is queued first
        self._closed = True
        with self._lock:
            self._conn.close()
