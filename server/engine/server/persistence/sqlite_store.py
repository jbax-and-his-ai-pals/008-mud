from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class EntityRecord:
    entity_id: str
    entity_type: str
    name: str
    components: Dict[str, Any]
    updated_at: float


class SqliteStore:
    """
    Lightweight SQLite persistence service with async write queue.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        self._lock = threading.Lock()
        self._write_queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._running = False
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
            self._conn.commit()

    def start_async_writer(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._writer_loop, daemon=True)
        self._worker.start()

    def stop_async_writer(self) -> None:
        if not self._running:
            return
        self._running = False
        self._write_queue.put(None)
        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None

    def _writer_loop(self) -> None:
        while self._running:
            task = self._write_queue.get()
            if task is None:
                break
            task_type = task.get("task_type", "entity")
            if task_type == "entity":
                self._write_entity_now(task)
            elif task_type == "world_cell":
                self._write_world_cell_now(task)

    def queue_entity_upsert(self, entity_id: str, entity_type: str, name: str, components: Dict[str, Any]) -> None:
        self._write_queue.put(
            {
                "task_type": "entity",
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": name,
                "components": components,
                "updated_at": time.time(),
            }
        )

    def queue_world_cell_upsert(self, cell_id: str, state: Dict[str, Any]) -> None:
        self._write_queue.put(
            {
                "task_type": "world_cell",
                "cell_id": cell_id,
                "state": state,
                "updated_at": time.time(),
            }
        )

    def _write_entity_now(self, payload: Dict[str, Any]) -> None:
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
                    json.dumps(payload["components"], default=str),
                    payload["updated_at"],
                ),
            )
            self._conn.commit()

    def flush(self, timeout_s: float = 2.0) -> bool:
        start = time.time()
        while not self._write_queue.empty():
            if time.time() - start > timeout_s:
                return False
            time.sleep(0.01)
        return True

    def _write_world_cell_now(self, payload: Dict[str, Any]) -> None:
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
                    json.dumps(payload["state"], default=str),
                    payload["updated_at"],
                ),
            )
            self._conn.commit()

    def load_world_cells(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute("SELECT cell_id, state_json FROM world_cells").fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

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
        with self._lock:
            self._conn.close()
