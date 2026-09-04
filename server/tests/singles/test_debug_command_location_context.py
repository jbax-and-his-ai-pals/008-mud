import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestDebugCommandLocationContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session = self.server.create_session()
        self.session_id = self.session.session_id
        self.server.execute_command(self.session_id, "char create TestPlayer")
        self.player = self.server.get_player_for_session(self.session_id)
        assert self.player is not None
        self.player.current_region_id = "town"
        self.player.current_room_id = "east_gate"
        # Intentionally diverge global world cursor from session player's location.
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"

    def tearDown(self) -> None:
        self.server.shutdown()

    def _room_item_count(self, region_id: str, room_id: str) -> int:
        region = self.server.world.regions.get(region_id)
        if region is None:
            return 0
        room = region.rooms.get(room_id)
        if room is None:
            return 0
        return len(room.items)

    def test_spawnstation_uses_session_player_location(self) -> None:
        player_count_before = self._room_item_count("town", "east_gate")
        global_count_before = self._room_item_count("town", "town_square")

        self.server.execute_command(self.session_id, "spawnstation anvil")

        self.assertEqual(player_count_before + 1, self._room_item_count("town", "east_gate"))
        self.assertEqual(global_count_before, self._room_item_count("town", "town_square"))

    def test_spawn_item_uses_session_player_location(self) -> None:
        player_count_before = self._room_item_count("town", "east_gate")
        global_count_before = self._room_item_count("town", "town_square")

        self.server.execute_command(self.session_id, "spawn item_anvil")

        self.assertEqual(player_count_before + 1, self._room_item_count("town", "east_gate"))
        self.assertEqual(global_count_before, self._room_item_count("town", "town_square"))

    def test_testrefactor_places_chest_in_session_player_location(self) -> None:
        player_count_before = self._room_item_count("town", "east_gate")
        global_count_before = self._room_item_count("town", "town_square")

        self.server.execute_command(self.session_id, "testrefactor")

        self.assertEqual(player_count_before + 1, self._room_item_count("town", "east_gate"))
        self.assertEqual(global_count_before, self._room_item_count("town", "town_square"))


if __name__ == "__main__":
    unittest.main()
