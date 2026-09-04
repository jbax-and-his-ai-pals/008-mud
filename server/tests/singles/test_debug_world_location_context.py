import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestDebugWorldLocationContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session_a = self.server.create_session(entitlements=["operator.world.debug"])
        self.session_b = self.server.create_session(entitlements=["operator.world.debug"])
        self.server.execute_command(self.session_a.session_id, "char create Alpha")
        self.server.execute_command(self.session_b.session_id, "char create Beta")
        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        assert self.player_a is not None
        assert self.player_b is not None

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_teleport_moves_invoking_session_player_only(self) -> None:
        self.player_a.current_region_id = "town"
        self.player_a.current_room_id = "town_square"
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "east_gate"

        self.server.execute_command(self.session_a.session_id, "tp town north_gate")

        self.assertEqual(("town", "north_gate"), (self.player_a.current_region_id, self.player_a.current_room_id))
        self.assertEqual(("town", "east_gate"), (self.player_b.current_region_id, self.player_b.current_room_id))

    def test_genregion_links_portal_from_invoking_player_room(self) -> None:
        self.player_a.current_region_id = "town"
        self.player_a.current_room_id = "east_gate"
        self.player_b.current_region_id = "town"
        self.player_b.current_room_id = "town_square"

        self.server.execute_command(self.session_a.session_id, "genregion forest 4")

        room_a = self.server.world.get_region("town").get_room("east_gate")
        room_b = self.server.world.get_region("town").get_room("town_square")
        self.assertIn("portal", room_a.exits)
        self.assertNotIn("portal", room_b.exits)


if __name__ == "__main__":
    unittest.main()
