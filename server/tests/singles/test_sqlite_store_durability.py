# tests/singles/test_sqlite_store_durability.py
"""What a persistence store owes the state it is handed.

`SqliteStore` queued writes for a background thread and lost them four ways: one
failed write killed the writer for the rest of the process; `stop` dropped every
write queued behind the one in flight; a queued "snapshot" held the live structure
and was serialised later, so it stored whatever the game had become; and `flush`
returned when the queue was empty, not when the write had landed. A store that is
about to carry a whole character and world has to be right about all four.
"""

import os
import shutil
import tempfile
import time
import unittest

from engine.server.persistence.sqlite_store import SqliteStore


class TestSqliteStoreDurability(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)  # registered first, runs last
        self.store = SqliteStore(os.path.join(self.dir, "state.sqlite3"))
        self.addCleanup(self.store.close)

    def _ids(self):
        return {record.entity_id for record in self.store.list_entities()}

    def test_one_failed_write_does_not_stop_the_ones_after_it(self):
        self.store.start_async_writer()
        self.store.queue_entity_upsert("a", "player", "first", {"n": 1})
        self.assertTrue(self.store.flush(5))
        self.store.queue_entity_upsert("bad", "player", None, {"n": 2})  # violates NOT NULL
        self.store.queue_entity_upsert("b", "player", "after the failure", {"n": 3})
        self.assertTrue(self.store.flush(5), "the writer is still alive to take the next write")
        self.assertEqual({"a", "b"}, self._ids())
        self.assertEqual(1, self.store.write_failures)
        self.assertIn("name", self.store.last_write_error.lower())

    def test_stopping_writes_everything_that_was_queued(self):
        self.store.start_async_writer()
        for i in range(300):
            self.store.queue_entity_upsert("e%d" % i, "player", "n%d" % i, {"i": i})
        self.store.stop_async_writer()
        self.assertEqual(300, len(self._ids()))

    def test_a_queued_snapshot_is_the_state_at_the_time_it_was_queued(self):
        live = {"flags": {"opened": False}, "hp": 10}
        self.store.queue_entity_upsert("p", "player", "hero", live)  # the writer has not started
        live["flags"]["opened"] = True  # the game moves on
        live["hp"] = 99
        self.store.start_async_writer()
        self.assertTrue(self.store.flush(5))
        self.assertEqual({"flags": {"opened": False}, "hp": 10}, self.store.load_entity("p").components)

    def test_flush_returns_when_the_write_has_landed_not_when_the_queue_is_empty(self):
        self.store.start_async_writer()
        original = self.store._write_entity_now

        def slow(payload):
            time.sleep(0.4)
            original(payload)

        self.store._write_entity_now = slow
        self.store.queue_entity_upsert("s", "player", "slow", {"n": 1})
        time.sleep(0.1)  # the writer has taken it and is inside the slow write
        self.assertTrue(self.store.flush(5))
        self.assertIsNotNone(self.store.load_entity("s"), "flush returned before the row existed")

    def test_closing_writes_what_is_still_queued(self):
        path = os.path.join(self.dir, "closing.sqlite3")
        store = SqliteStore(path)
        store.queue_entity_upsert("orphan", "player", "queued with no writer", {"n": 1})  # no writer was ever started
        store.close()
        reopened = SqliteStore(path)
        self.addCleanup(reopened.close)
        self.assertEqual({"orphan"}, {record.entity_id for record in reopened.list_entities()})

    def test_world_state_round_trips_and_a_missing_key_is_none(self):
        self.store.start_async_writer()
        self.store.queue_world_state("world", {"rooms": {"a:b": {"exits": {"down": "a:c"}}}})
        self.assertTrue(self.store.flush(5))
        self.assertEqual({"rooms": {"a:b": {"exits": {"down": "a:c"}}}}, self.store.load_world_state("world"))
        self.assertIsNone(self.store.load_world_state("missing"))

    def test_the_latest_world_state_wins(self):
        self.store.start_async_writer()
        self.store.queue_world_state("world", {"tick": 1})
        self.store.queue_world_state("world", {"tick": 2})
        self.assertTrue(self.store.flush(5))
        self.assertEqual({"tick": 2}, self.store.load_world_state("world"))

    def test_closing_twice_is_harmless(self):
        self.store.start_async_writer()
        self.store.queue_entity_upsert("a", "player", "x", {})
        self.store.close()
        self.store.close()
        # a queued write after close does not raise into the caller
        self.store.queue_entity_upsert("late", "player", "x", {})


if __name__ == "__main__":
    unittest.main()
