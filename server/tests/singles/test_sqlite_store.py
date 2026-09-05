# tests/singles/test_sqlite_store.py
"""Coverage for engine/server/persistence/sqlite_store.py: file-path db init
(parent-directory creation), the async writer's start/stop no-op guards and
worker-join branch, the writer loop's entity/world_cell dispatch and
None-sentinel break, flush()'s timeout path, and load_entity/list_entities'
found/missing and filtered/unfiltered branches."""

import os
import shutil
import tempfile
import time
import unittest

from engine.server.persistence.sqlite_store import SqliteStore


class TestSqliteStoreInit(unittest.TestCase):
    def test_file_path_creates_parent_directory(self):
        tmp_dir = tempfile.mkdtemp()
        db_path = os.path.join(tmp_dir, "nested", "test.db")
        store = SqliteStore(db_path)
        try:
            self.assertTrue(os.path.isdir(os.path.dirname(db_path)))
        finally:
            store.close()
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestSqliteStoreAsyncWriter(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_start_is_a_noop_when_already_running(self):
        self.store.start_async_writer()
        self.store.start_async_writer()  # should not spawn a second worker
        self.store.stop_async_writer()

    def test_stop_is_a_noop_when_not_running(self):
        self.store.stop_async_writer()  # never started -- early return

    def test_stop_without_a_worker_thread_skips_join(self):
        # Simulate _running=True without ever going through start_async_writer,
        # so self._worker stays None -- exercises the "if self._worker" False branch.
        self.store._running = True
        self.store.stop_async_writer()
        self.assertFalse(self.store._running)

    def test_start_stop_processes_queued_entity_write_end_to_end(self):
        self.store.start_async_writer()
        self.store.queue_entity_upsert("e_async", "npc", "Alice", {"hp": 10})
        self.assertTrue(self.store.flush(timeout_s=2.0))
        record = self.store.load_entity("e_async")
        self.assertIsNotNone(record)
        self.assertEqual(record.name, "Alice")
        self.store.stop_async_writer()


class TestWriterLoopDirect(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_returns_immediately_when_not_running(self):
        self.store._running = False
        self.store._writer_loop()  # must not block on an empty queue

    def test_processes_entity_and_world_cell_tasks_then_breaks_on_none(self):
        self.store._running = True
        self.store._write_queue.put({
            "task_type": "entity", "entity_id": "e_direct", "entity_type": "npc",
            "name": "Bob", "components": {}, "updated_at": time.time(),
        })
        self.store._write_queue.put({
            "task_type": "world_cell", "cell_id": "c_direct",
            "state": {"foo": "bar"}, "updated_at": time.time(),
        })
        self.store._write_queue.put(None)

        self.store._writer_loop()

        self.assertIsNotNone(self.store.load_entity("e_direct"))
        self.assertIn("c_direct", self.store.load_world_cells())

    def test_unrecognized_task_type_is_silently_ignored(self):
        self.store._running = True
        self.store._write_queue.put({"task_type": "something_else"})
        self.store._write_queue.put(None)
        self.store._writer_loop()  # neither branch fires; loop just continues


class TestFlush(unittest.TestCase):
    def test_times_out_when_queue_never_drains(self):
        store = SqliteStore(":memory:")
        try:
            store.queue_entity_upsert("e_stuck", "npc", "Ghost", {})  # no writer running
            result = store.flush(timeout_s=0.05)
            self.assertFalse(result)
        finally:
            store.close()

    def test_returns_true_immediately_when_queue_already_empty(self):
        store = SqliteStore(":memory:")
        try:
            self.assertTrue(store.flush(timeout_s=1.0))
        finally:
            store.close()


class TestLoadAndListEntities(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_load_entity_returns_none_when_missing(self):
        self.assertIsNone(self.store.load_entity("does_not_exist"))

    def test_load_entity_returns_record_when_present(self):
        self.store._write_entity_now({
            "entity_id": "e_load", "entity_type": "npc", "name": "Zed",
            "components": {"x": 1}, "updated_at": 123.0,
        })
        record = self.store.load_entity("e_load")
        self.assertEqual(record.name, "Zed")
        self.assertEqual(record.components, {"x": 1})

    def test_list_entities_filters_by_type_and_lists_all(self):
        self.store._write_entity_now({
            "entity_id": "e_npc", "entity_type": "npc", "name": "A",
            "components": {}, "updated_at": 1.0,
        })
        self.store._write_entity_now({
            "entity_id": "e_item", "entity_type": "item", "name": "B",
            "components": {}, "updated_at": 1.0,
        })
        npcs = self.store.list_entities(entity_type="npc")
        self.assertEqual([r.entity_id for r in npcs], ["e_npc"])
        all_entities = self.store.list_entities()
        self.assertEqual({r.entity_id for r in all_entities}, {"e_npc", "e_item"})


if __name__ == "__main__":
    unittest.main()
