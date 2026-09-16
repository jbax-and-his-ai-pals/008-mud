"""P7 underground layer: the caves region's subterranean lake/river gap.

ROADMAP.md's underground-layer item called out "deeper subterranean water"
as the one still-missing biome from WORLD_DESIGN.md's palette (Sewers,
catacombs, mines, and natural caverns were already covered elsewhere).
This is a compact wing off the caves region's flooded mine bottom: a real
lake destination, not just a connector room, with its own discovery."""

from pathlib import Path
import unittest

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestSunkenLake(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_lake_wing_is_reachable_from_the_flooded_mine_bottom(self) -> None:
        caves = self.server.world.get_region("caves")
        self.assertIsNotNone(caves)
        for room_id in ("sunken_lake_landing", "sunken_lake", "drowned_gallery"):
            with self.subTest(room_id=room_id):
                self.assertIsNotNone(caves.get_room(room_id))

        path = self.server.world.find_path("caves", "mine_lower_level", "caves", "drowned_gallery")
        self.assertIsNotNone(path, "the lake wing must be reachable from the mine's flooded bottom")

    def test_visiting_the_lake_pays_landmark_xp_once(self) -> None:
        session = self.server.create_session(player_id="lake_explorer")
        self.server.execute_command(session.session_id, "char create Rowan")
        player = self.server.get_player_for_session(session.session_id)
        player.current_region_id = "caves"
        player.current_room_id = "mine_lower_level"
        self.server.world.current_region_id = "caves"
        self.server.world.current_room_id = "mine_lower_level"

        result = self.server.world.change_room("down", player)
        self.assertIn("SUNKEN LAKE LANDING", result.upper())
        self.assertIn("landmark:caves:sunken_lake_landing", player.advancement_entries)

        # Leaving and coming back must not pay the landing's landmark twice.
        entries_after_first_visit = set(player.advancement_entries)
        self.server.world.change_room("up", player)
        second_visit_result = self.server.world.change_room("down", player)
        self.assertNotIn("reached level", second_visit_result.lower())
        self.assertEqual(
            {k for k in entries_after_first_visit if k != "landmark:caves:mine_lower_level"},
            {k for k in player.advancement_entries if k != "landmark:caves:mine_lower_level"},
        )

    def test_drowned_gallery_pearl_triggers_the_sunken_lake_discovery(self) -> None:
        session = self.server.create_session(player_id="lake_diver")
        self.server.execute_command(session.session_id, "char create Diver")
        player = self.server.get_player_for_session(session.session_id)

        pearl = ItemFactory.create_item_from_template("item_cave_pearl", self.server.world)
        self.assertIsNotNone(pearl)
        player.inventory.add_item(pearl)
        note = self.server.discovery_manager.handle_item_discovery(player, pearl)
        self.assertIn("New discovery", note)
        self.assertIn("sunken_lake", player.discoveries)

    def test_drowned_gallery_item_placement_matches_the_room(self) -> None:
        caves = self.server.world.get_region("caves")
        gallery = caves.get_room("drowned_gallery")
        item_ids = [item.obj_id for item in gallery.items]
        self.assertIn("item_cave_pearl", item_ids)


if __name__ == "__main__":
    unittest.main()
