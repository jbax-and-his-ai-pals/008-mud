"""Contract tests for content-set-scoped runtime save storage."""

import json
import tempfile
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPOSITORY_ROOT / "content_sets" / "modern_capsule"


class TestContentSetSaveStorage(unittest.TestCase):
    def _server(self, content_set: Path, save_directory: Path | None) -> HeadlessServer:
        kwargs = {} if save_directory is None else {"save_directory": str(save_directory)}
        return HeadlessServer(
            db_path=":memory:",
            content_set_path=str(content_set),
            deterministic_test_mode=True,
            **kwargs,
        )

    def test_save_is_written_to_explicit_runtime_directory_not_authored_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            save_directory = Path(temporary_directory) / "player-state"
            server = self._server(FANTASY_FRONTIER, save_directory)
            try:
                session = server.create_session(player_id="storage_contract_player")
                server.execute_command(session.session_id, "char create Rowan")
                player = server.get_player_for_session(session.session_id)
                self.assertTrue(server.world.save_game("contract.json", player=player))
            finally:
                server.shutdown()

            saved_path = save_directory / "contract.json"
            self.assertTrue(saved_path.is_file())
            self.assertEqual("fantasy_frontier", json.loads(saved_path.read_text(encoding="utf-8"))["content_set"]["id"])
            self.assertFalse((FANTASY_FRONTIER / "data" / "saves" / "contract.json").exists())

    def test_default_save_directories_are_partitioned_by_content_set(self) -> None:
        fantasy = self._server(FANTASY_FRONTIER, None)
        modern = self._server(MODERN_CAPSULE, None)
        try:
            fantasy_directory = Path(fantasy.world.save_directory)
            modern_directory = Path(modern.world.save_directory)
            self.assertNotEqual(fantasy_directory, modern_directory)
            self.assertEqual("fantasy_frontier", fantasy_directory.name)
            self.assertEqual("modern_capsule", modern_directory.name)
            self.assertNotIn("server\\data", str(fantasy_directory).lower())
        finally:
            fantasy.shutdown()
            modern.shutdown()

    def test_load_does_not_fall_back_to_current_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            server = self._server(FANTASY_FRONTIER, Path(temporary_directory))
            try:
                self.assertIsNone(server.world.save_manager._resolve_load_path("not-present.json"))
            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()