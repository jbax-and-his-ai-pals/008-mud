import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from engine.server.headless_server import HeadlessServer


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPOSITORY_ROOT / "content_sets" / "modern_capsule"


class TestContentSetSaveIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.save_name = f"content_set_save_{uuid.uuid4().hex}.json"
        self._runtime_state = tempfile.TemporaryDirectory()
        self.save_directory = Path(self._runtime_state.name) / "saves"
        self.save_path = self.save_directory / self.save_name
        self.package_root = REPOSITORY_ROOT / "tmp" / f"alternate_save_content_set_{uuid.uuid4().hex}"
        self.addCleanup(self._runtime_state.cleanup)
        self.addCleanup(lambda: shutil.rmtree(self.package_root, ignore_errors=True))

    def _server(self, content_set: Path) -> HeadlessServer:
        return HeadlessServer(
            db_path=":memory:",
            content_set_path=str(content_set),
            save_directory=str(self.save_directory),
            deterministic_test_mode=True,
        )

    def _alternate_package(self) -> Path:
        shutil.copytree(FANTASY_FRONTIER, self.package_root)
        manifest_path = self.package_root / "content_set.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["id"] = "alternate_save_game"
        manifest["title"] = "Alternate Save Game"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return self.package_root
    def test_save_records_content_set_and_resumes_only_in_that_game(self) -> None:
        source = self._server(FANTASY_FRONTIER)
        try:
            session = source.create_session(player_id="save_isolation_player")
            source.execute_command(session.session_id, "char create Rowan")
            source.execute_command(session.session_id, "north")
            self.assertTrue(source.world.save_game(self.save_name, player=source.get_player_for_session(session.session_id)))
        finally:
            source.shutdown()

        payload = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual({"id": "fantasy_frontier", "version": "0.1.0"}, payload["content_set"])

        matching = self._server(FANTASY_FRONTIER)
        try:
            loaded, _time_state, _weather_state = matching.world.load_save_game(self.save_name)
            self.assertTrue(loaded)
            self.assertEqual("north_gate_road", matching.world.player.current_room_id)
        finally:
            matching.shutdown()

        mismatched = self._server(self._alternate_package())
        try:
            loaded, _time_state, _weather_state = mismatched.world.load_save_game(self.save_name)
            self.assertFalse(loaded)
        finally:
            mismatched.shutdown()

    def test_modern_save_omits_disabled_rpg_aspects(self) -> None:
        server = self._server(MODERN_CAPSULE)
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
        for system in ("magic", "combat", "progression", "economy", "quests"):
            self.assertNotIn(system, gameplay)


if __name__ == "__main__":
    unittest.main()