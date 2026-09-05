import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.config import SAVE_GAME_DIR
from engine.server.headless_server import HeadlessServer


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPOSITORY_ROOT / "content_sets" / "modern_capsule"


class TestContentSetSaveCompatibility(unittest.TestCase):
    def setUp(self) -> None:
        self.save_name = f"content_set_save_{uuid.uuid4().hex}.json"
        self.save_path = Path(SAVE_GAME_DIR) / self.save_name
        self.package_root = REPOSITORY_ROOT / "tmp" / f"alternate_save_content_set_{uuid.uuid4().hex}"
        self.addCleanup(lambda: self.save_path.unlink(missing_ok=True))
        self.addCleanup(lambda: shutil.rmtree(self.package_root, ignore_errors=True))

    def _alternate_package(self) -> Path:
        self.package_root.mkdir(parents=True, exist_ok=True)
        rules_dir = self.package_root / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        ruleset_path = rules_dir / "ruleset.json"
        ruleset_path.write_text(
            json.dumps(
                {
                    "progression_model": "none",
                    "systems": {
                        "combat": {"enabled": False},
                        "magic": {"enabled": False},
                        "crafting": {"enabled": False},
                        "quests": {"enabled": False},
                        "economy": {"enabled": False},
                    },
                }
            ),
            encoding="utf-8",
        )
        manifest = {
            "id": "alternate_save_game",
            "title": "Alternate Save Game",
            "version": "0.1.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "paths": {
                "data_root": str((FANTASY_FRONTIER / "data").resolve()),
                "ruleset": str(ruleset_path.resolve()),
                "presentation": str((FANTASY_FRONTIER / "presentation" / "default.json").resolve()),
            },
            "start": {"scenario_id": "arrival_in_town", "region_id": "town", "room_id": "town_square"},
            "capabilities": ["inventory"],
        }
        (self.package_root / "content_set.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return self.package_root

    def test_save_records_content_set_and_resumes_only_in_that_game(self) -> None:
        source = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        try:
            session = source.create_session(player_id="save_compatibility_player")
            source.execute_command(session.session_id, "char create Rowan")
            source.execute_command(session.session_id, "north")
            player = source.get_player_for_session(session.session_id)
            self.assertTrue(source.world.save_game(self.save_name, player=player))
        finally:
            source.shutdown()

        payload = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual({"id": "fantasy_frontier", "version": "0.1.0"}, payload["content_set"])

        matching = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        try:
            loaded, _time_state, _weather_state = matching.world.load_save_game(self.save_name)
            self.assertTrue(loaded)
            self.assertEqual("north_gate_road", matching.world.player.current_room_id)
        finally:
            matching.shutdown()

        mismatched = HeadlessServer(db_path=":memory:", content_set_path=str(self._alternate_package()), deterministic_test_mode=True)
        try:
            loaded, _time_state, _weather_state = mismatched.world.load_save_game(self.save_name)
            self.assertFalse(loaded)
        finally:
            mismatched.shutdown()

    def test_modern_save_omits_disabled_rpg_aspects(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=str(MODERN_CAPSULE), deterministic_test_mode=True)
        try:
            session = server.create_session(player_id="modern_save_player")
            server.execute_command(session.session_id, "char create Avery")
            self.assertTrue(server.world.save_game(self.save_name, player=server.get_player_for_session(session.session_id)))
        finally:
            server.shutdown()

        player = json.loads(self.save_path.read_text(encoding="utf-8"))["player"]
        self.assertNotIn("mana", player)
        self.assertNotIn("level", player)
        gameplay = player["gameplay"]
        self.assertNotIn("magic", gameplay)
        self.assertNotIn("combat", gameplay)
        self.assertNotIn("progression", gameplay)
        self.assertNotIn("economy", gameplay)
        self.assertNotIn("quests", gameplay)


if __name__ == "__main__":
    unittest.main()
