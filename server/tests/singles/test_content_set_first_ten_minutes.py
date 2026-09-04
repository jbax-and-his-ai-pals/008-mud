"""Deterministic player-facing acceptance scenarios for canonical content sets."""

import json
import unittest
import uuid
from pathlib import Path

from engine.config import SAVE_GAME_DIR
from engine.server.headless_server import HeadlessServer


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPOSITORY_ROOT / "content_sets" / "modern_capsule"


class TestContentSetFirstTenMinutes(unittest.TestCase):
    def setUp(self) -> None:
        self.save_name = f"acceptance_journey_{uuid.uuid4().hex}.json"
        self.save_path = Path(SAVE_GAME_DIR) / self.save_name
        self.addCleanup(lambda: self.save_path.unlink(missing_ok=True))

    @staticmethod
    def _text(events: list[dict]) -> str:
        return "\n".join(str(event["payload"]) for event in events if event.get("type") == "text")

    def test_fantasy_first_ten_minutes(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True
        )
        try:
            session = server.create_session(player_id="fantasy_acceptance_player")
            created = server.execute_command(session.session_id, "char create Rowan")
            self.assertIn("Welcome to Riverside", self._text(created))

            self.assertIn("Elder Thorne", self._text(server.execute_command(session.session_id, "talk elder")))
            self.assertIn("rusty dagger", self._text(server.execute_command(session.session_id, "inventory")))
            self.assertIn("NORTH GATE ROAD", self._text(server.execute_command(session.session_id, "north")))
            self.assertIn("TOWN SQUARE", self._text(server.execute_command(session.session_id, "south")))

            player = server.get_player_for_session(session.session_id)
            self.assertIsNotNone(player)
            self.assertTrue(server.world.save_game(self.save_name, player=player))
        finally:
            server.shutdown()

        saved = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual("fantasy_frontier", saved["content_set"]["id"])
        self.assertEqual("town_square", saved["player"]["current_location"]["room_id"])

        restored = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True
        )
        try:
            loaded, _time_state, _weather_state = restored.world.load_save_game(self.save_name)
            self.assertTrue(loaded)
            self.assertEqual("Rowan", restored.world.player.name)
            self.assertEqual("town_square", restored.world.player.current_room_id)
        finally:
            restored.shutdown()

    def test_modern_first_ten_minutes(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(MODERN_CAPSULE), deterministic_test_mode=True
        )
        try:
            session = server.create_session(player_id="modern_acceptance_player")
            created = server.execute_command(session.session_id, "char create Avery")
            self.assertIn("A Connection Across Town", self._text(created))
            self.assertIn("Morning.", self._text(server.execute_command(session.session_id, "talk maya")))
            self.assertIn("espresso machine", self._text(server.execute_command(session.session_id, "east")))
            self.assertIn("Commuters cross an open plaza", self._text(server.execute_command(session.session_id, "west")))

            player = server.get_player_for_session(session.session_id)
            self.assertIsNotNone(player)
            self.assertTrue(server.world.save_game(self.save_name, player=player))
        finally:
            server.shutdown()

        saved = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual("modern_capsule", saved["content_set"]["id"])
        self.assertEqual("transit_plaza", saved["player"]["current_location"]["room_id"])
        self.assertNotIn("magic", saved["player"]["gameplay"])


if __name__ == "__main__":
    unittest.main()
