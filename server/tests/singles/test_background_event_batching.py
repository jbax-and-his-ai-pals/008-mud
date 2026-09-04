import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestFlushBackgroundBatch(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_empty_batch_returns_empty_list(self):
        self.assertEqual([], self.server._flush_background_batch(self.session.session_id))

    def test_disabled_coalescing_returns_events_verbatim(self):
        self.server._background_batch_enabled = False
        self.server._background_event_batch.append(self.server._event("text", self.session.session_id, "line one"))
        self.server._background_event_batch.append(self.server._event("text", self.session.session_id, "line two"))
        flushed = self.server._flush_background_batch(self.session.session_id)
        self.assertEqual(2, len(flushed))
        self.assertEqual([], self.server._background_event_batch)

    def test_consecutive_text_events_are_coalesced(self):
        sid = self.session.session_id
        self.server._background_event_batch.append(self.server._event("text", sid, "line one"))
        self.server._background_event_batch.append(self.server._event("text", sid, "line two"))
        flushed = self.server._flush_background_batch(sid)
        self.assertEqual(1, len(flushed))
        self.assertEqual("line one\nline two", flushed[0]["payload"])

    def test_non_text_events_break_up_coalescing(self):
        sid = self.session.session_id
        self.server._background_event_batch.append(self.server._event("text", sid, "before"))
        self.server._background_event_batch.append(self.server._event("world_state", sid, {"tick": 1}))
        self.server._background_event_batch.append(self.server._event("text", sid, "after"))
        flushed = self.server._flush_background_batch(sid)
        self.assertEqual(3, len(flushed))
        self.assertEqual("before", flushed[0]["payload"])
        self.assertEqual("world_state", flushed[1]["type"])
        self.assertEqual("after", flushed[2]["payload"])

    def test_text_events_for_other_sessions_are_not_coalesced_into_this_ones_batch(self):
        other = self.server.create_session()
        sid = self.session.session_id
        self.server._background_event_batch.append(self.server._event("text", sid, "mine"))
        self.server._background_event_batch.append(self.server._event("text", other.session_id, "theirs"))
        flushed = self.server._flush_background_batch(sid)
        payload_types_and_sessions = [(e["type"], e["session_id"]) for e in flushed]
        self.assertIn(("text", other.session_id), payload_types_and_sessions)


class TestCombatAdjacentMessageFilter(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_combat_message_is_not_filtered_when_combat_is_enabled(self):
        self.server.feature_profile.combat_mode = "enabled"
        self.assertFalse(self.server._is_combat_adjacent_message("The rat attacks you for 3 damage."))

    def test_combat_message_is_filtered_when_combat_is_disabled(self):
        self.server.feature_profile.combat_mode = "disabled"
        self.assertTrue(self.server._is_combat_adjacent_message("The rat attacks you for 3 damage."))

    def test_non_combat_message_is_never_filtered(self):
        self.server.feature_profile.combat_mode = "disabled"
        self.assertFalse(self.server._is_combat_adjacent_message("The sun rises over the town."))

    def test_empty_message_is_never_filtered(self):
        self.server.feature_profile.combat_mode = "disabled"
        self.assertFalse(self.server._is_combat_adjacent_message(""))


if __name__ == "__main__":
    unittest.main()
