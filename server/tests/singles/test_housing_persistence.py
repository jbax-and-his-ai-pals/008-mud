"""End-to-end coverage for buying a house and it surviving save/load.

Uses two separate HeadlessServer instances against the same save directory
(rather than reusing one process's in-memory World) so the static "town"
region is genuinely rebuilt fresh from content-set JSON between save and
load -- the same real-world timing test_instance_entry_exit_persistence.py
proves the underlying fix against directly, exercised here through the
actual housing feature and command surface a player would use."""

import tempfile
import unittest
from pathlib import Path

from engine.server.content_set import load_content_set
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestHousingPersistence(unittest.TestCase):
    def test_buy_house_survives_save_and_a_fresh_server_load(self) -> None:
        definition, issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(definition, issues)

        with tempfile.TemporaryDirectory() as save_directory:
            server = HeadlessServer(
                save_file="housetest.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                session = server.create_session(player_id="house_buyer")
                server.execute_command(session.session_id, "char create Rowan")
                player = server.get_player_for_session(session.session_id)
                player.runtime_state.gold = 1000
                player.current_region_id = "town"
                player.current_room_id = "residential_street_east"

                server.execute_command(session.session_id, "northeast")
                self.assertEqual(("town", "player_house_exterior"), (player.current_region_id, player.current_room_id))

                bought = server.execute_command(session.session_id, "buy house")
                bought_text = "\n".join(str(event["payload"]) for event in bought)
                self.assertIn("You pay 500 gold", bought_text)
                self.assertEqual(500, player.runtime_state.gold)
                self.assertEqual(1, player.inventory.count_item("item_house_key_starter"))

                entered = server.execute_command(session.session_id, "in")
                entered_text = "\n".join(str(event["payload"]) for event in entered)
                self.assertIn("Your House", entered_text)
                self.assertEqual(("dynamic_player_house", "interior"), (player.current_region_id, player.current_room_id))

                player_id_before = player.obj_id
                self.assertTrue(server.world.save_game("housetest.json"))
            finally:
                server.shutdown()

            # A brand-new server/world, forcing a real rebuild of every
            # static region from content-set JSON -- not the same in-memory
            # objects the first server mutated.
            server2 = HeadlessServer(
                save_file="housetest.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                vacant_lot_before_load = server2.world.get_region("town").get_room("player_house_exterior")
                self.assertNotIn("in", vacant_lot_before_load.exits)

                success, _time_state, _weather_state = server2.world.load_save_game("housetest.json")
                self.assertTrue(success)

                loaded_player = server2.world.player
                self.assertIsNotNone(loaded_player)
                self.assertEqual(player_id_before, loaded_player.obj_id)
                self.assertEqual(1, loaded_player.inventory.count_item("item_house_key_starter"))

                house_region = server2.world.get_region("dynamic_player_house")
                self.assertIsNotNone(house_region)
                self.assertEqual(loaded_player.obj_id, house_region.properties.get("owner_player_id"))

                vacant_lot = server2.world.get_region("town").get_room("player_house_exterior")
                self.assertEqual("dynamic_player_house:interior", vacant_lot.exits.get("in"))
                lock = vacant_lot.properties.get("exit_requirements", {}).get("in", {})
                self.assertEqual("locked", lock.get("type"))
                self.assertEqual("item_house_key_starter", lock.get("key_id"))
            finally:
                server2.shutdown()


if __name__ == "__main__":
    unittest.main()
