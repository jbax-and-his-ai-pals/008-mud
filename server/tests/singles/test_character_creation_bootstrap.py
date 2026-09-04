import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestCharacterCreationBootstrap(unittest.TestCase):
    def test_session_starts_without_player_when_required(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, require_character_creation=True)
        try:
            session = server.create_session()
            self.assertIsNone(server.get_player_for_session(session.session_id))
            self.assertIsNone(getattr(server.world, "player", None))
        finally:
            server.shutdown()

    def test_non_creation_commands_prompt_for_character(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, require_character_creation=True)
        try:
            session = server.create_session()
            events = server.execute_command(session.session_id, "look")
            text_payloads = [ev.get("payload", "") for ev in events if ev.get("type") == "text"]
            self.assertTrue(any("No character yet. Use: char create <name>" in str(payload) for payload in text_payloads))
        finally:
            server.shutdown()

    def test_character_create_enables_normal_commands(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, require_character_creation=True)
        try:
            session = server.create_session()
            create_events = server.execute_command(session.session_id, "char create Tester")
            create_texts = [ev.get("payload", "") for ev in create_events if ev.get("type") == "text"]
            self.assertTrue(any("Character created: Tester" in str(payload) for payload in create_texts))

            player = server.get_player_for_session(session.session_id)
            self.assertIsNotNone(player)
            self.assertEqual("Tester", getattr(player, "name", ""))

            look_events = server.execute_command(session.session_id, "look")
            look_texts = [ev.get("payload", "") for ev in look_events if ev.get("type") == "text"]
            self.assertFalse(any("No character yet" in str(payload) for payload in look_texts))
            self.assertTrue(any(ev.get("type") == "nearby" for ev in look_events))
        finally:
            server.shutdown()

    def test_character_create_uses_bootstrap_start_location_for_spawn_and_respawn(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, require_character_creation=True)
        try:
            server.world.initialize_new_world(start_region="casino", start_room="lobby")
            session = server.create_session()
            server.execute_command(session.session_id, "char create Traveler")

            player = server.get_player_for_session(session.session_id)
            self.assertIsNotNone(player)
            self.assertEqual("casino", getattr(player, "current_region_id", None))
            self.assertEqual("lobby", getattr(player, "current_room_id", None))
            self.assertEqual("casino", getattr(player, "respawn_region_id", None))
            self.assertEqual("lobby", getattr(player, "respawn_room_id", None))
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
