import unittest
from pathlib import Path
from unittest.mock import Mock

from engine.npcs.npc_factory import NPCFactory
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


class TestWorldTickMessageRoutingByRoom(unittest.TestCase):
    """Regression coverage for a bug found during live playtesting: a hostile's
    attack message (and other room-scoped world-tick messages) was tagged with
    whichever session's poll happened to trigger the periodic world.update(),
    not the session(s) actually watching the room the event occurred in."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True
        )
        self.session_a = self.server.create_session(player_id="route_player_a")
        self.session_b = self.server.create_session(player_id="route_player_b")
        for session in (self.session_a, self.session_b):
            self.server.mark_session_connected(session.session_id)
        self.server.execute_command(self.session_a.session_id, "char create RouteA")
        self.server.execute_command(self.session_b.session_id, "char create RouteB")
        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        self.assertIsNotNone(self.player_a)
        self.assertIsNotNone(self.player_b)

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_room_scoped_combat_message_is_not_delivered_to_a_session_in_another_room(self):
        # Put player_b somewhere else so only player_a's session should ever
        # see the goblin's attack message.
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "market_square"

        goblin = NPCFactory.create_npc_from_template(
            "goblin", self.server.world, instance_id="route_goblin"
        )
        self.assertIsNotNone(goblin)
        goblin.current_region_id = self.player_a.current_region_id
        goblin.current_room_id = self.player_a.current_room_id
        self.server.world.add_npc(goblin)
        goblin.enter_combat(self.player_a)
        goblin.combat_cooldown = 0.0
        goblin.attack_cooldown = 0.0
        goblin.last_attack_time = 0.0
        goblin.last_combat_action = 0.0

        self.server.world.last_update_time = 0.0
        # Session B's poll is the one that happens to trigger the periodic
        # world tick -- it must not receive the goblin's combat text just
        # because its poll was the one that ran the tick. (Session B may
        # legitimately still receive unrelated global background events,
        # like time-of-day/weather ticks tagged to the calling session --
        # this only asserts on the room-scoped combat message itself.)
        self.server.tick(self.session_b.session_id)

        batch = self.server._background_event_batch
        session_a_texts = [
            ev.get("payload", "") for ev in batch
            if ev.get("session_id") == self.session_a.session_id and ev.get("type") == "text"
        ]
        session_b_texts = [
            ev.get("payload", "") for ev in batch
            if ev.get("session_id") == self.session_b.session_id and ev.get("type") == "text"
        ]
        self.assertTrue(any("goblin" in text.lower() for text in session_a_texts))
        self.assertFalse(any("goblin" in text.lower() for text in session_b_texts))

    def test_moving_npc_message_routes_to_the_room_it_left(self):
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "market_square"

        goblin = NPCFactory.create_npc_from_template(
            "goblin", self.server.world, instance_id="routing_flee_goblin"
        )
        self.assertIsNotNone(goblin)
        goblin.current_region_id = self.player_a.current_region_id
        goblin.current_room_id = self.player_a.current_room_id
        starting_room = goblin.current_room_id

        def flee_during_update(_world, _current_time):
            goblin.current_room_id = "north_gate_road"
            return "The goblin flees north!"

        goblin.update = Mock(side_effect=flee_during_update)
        self.server.world.add_npc(goblin)
        self.server.world.last_update_time = 0.0
        self.server.tick(self.session_b.session_id)

        session_a_texts = [
            ev.get("payload", "") for ev in self.server._background_event_batch
            if ev.get("session_id") == self.session_a.session_id and ev.get("type") == "text"
        ]
        session_b_texts = [
            ev.get("payload", "") for ev in self.server._background_event_batch
            if ev.get("session_id") == self.session_b.session_id and ev.get("type") == "text"
        ]
        self.assertNotEqual(starting_room, goblin.current_room_id)
        self.assertIn("The goblin flees north!", session_a_texts)
        self.assertNotIn("The goblin flees north!", session_b_texts)


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
