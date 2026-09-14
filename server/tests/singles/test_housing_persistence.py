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

from engine.items.item_factory import ItemFactory
from engine.items.inventory import Inventory
from engine.server.content_set import load_content_set
from engine.server.headless_server import HeadlessServer
from engine.world.housing_manager import HOUSE_ENTRY_SENTINEL


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestHousingPersistence(unittest.TestCase):
    def test_buy_house_requires_space_for_its_key_before_charging_or_building(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="full_pack_house_buyer")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.runtime_state.gold = 1000
            player.inventory = Inventory(max_slots=1, max_weight=100.0)
            filler = ItemFactory.create_item_from_template("item_starter_dagger", server.world)
            player.inventory.add_item(filler)
            player.current_region_id = "town"
            player.current_room_id = "player_house_exterior"

            result = server.execute_command(session.session_id, "buy house")

            self.assertIn("room for the house key", "\n".join(str(event["payload"]) for event in result))
            self.assertEqual(1000, player.runtime_state.gold)
            self.assertIsNone(server.world.housing_manager.get_owned_house(player))
            exterior = server.world.get_region("town").get_room("player_house_exterior")
            self.assertNotIn("in", exterior.exits)
        finally:
            server.shutdown()

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

                player_id_before = player.obj_id
                expected_region_id = f"dynamic_player_house_{player_id_before}"

                entered = server.execute_command(session.session_id, "in")
                entered_text = "\n".join(str(event["payload"]) for event in entered)
                self.assertIn("Your House", entered_text)
                self.assertEqual((expected_region_id, "interior"), (player.current_region_id, player.current_room_id))

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

                house_region = server2.world.get_region(expected_region_id)
                self.assertIsNotNone(house_region)
                self.assertEqual(loaded_player.obj_id, house_region.properties.get("owner_player_id"))

                # The shared exterior's entry exit is a fixed sentinel,
                # resolved per-player by World.change_room -- not a literal
                # per-owner destination, and not a lock/key on the shared
                # room (that can't be scoped to one owner).
                vacant_lot = server2.world.get_region("town").get_room("player_house_exterior")
                self.assertEqual(HOUSE_ENTRY_SENTINEL, vacant_lot.exits.get("in"))
                self.assertNotIn("in", vacant_lot.properties.get("exit_requirements", {}))

                restored_key = loaded_player.inventory.find_item_by_id("item_house_key_starter")
                self.assertIsNotNone(restored_key)
                self.assertEqual(house_region.obj_id, restored_key.get_property("target_id"))
            finally:
                server2.shutdown()

    def test_house_tier_2_branch_survives_save_and_a_fresh_server_load(self) -> None:
        with tempfile.TemporaryDirectory() as save_directory:
            server = HeadlessServer(
                save_file="housetest_tier2.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                session = server.create_session(player_id="house_expander")
                server.execute_command(session.session_id, "char create Rowan")
                player = server.get_player_for_session(session.session_id)
                player.runtime_state.gold = 1000
                player.current_region_id = "town"
                player.current_room_id = "residential_street_east"
                server.execute_command(session.session_id, "northeast")
                server.execute_command(session.session_id, "buy house")

                # Ambiguous without a branch: two options exist for tier 2.
                ambiguous = server.execute_command(session.session_id, "expand house")
                self.assertIn(
                    "Which upgrade did you have in mind?",
                    "\n".join(str(event["payload"]) for event in ambiguous),
                )

                for item_id, quantity in (("item_softwood", 6), ("item_wild_herbs", 5)):
                    item = ItemFactory.create_item_from_template(item_id, server.world)
                    player.inventory.add_item(item, quantity)

                expanded = server.execute_command(session.session_id, "expand house garden")
                expanded_text = "\n".join(str(event["payload"]) for event in expanded)
                self.assertIn("Garden Cottage", expanded_text)
                self.assertEqual(250, player.runtime_state.gold)
                self.assertEqual(0, player.inventory.count_item("item_softwood"))
                self.assertEqual(0, player.inventory.count_item("item_wild_herbs"))

                expected_region_id = f"dynamic_player_house_{player.obj_id}"
                self.assertTrue(server.world.save_game("housetest_tier2.json"))
            finally:
                server.shutdown()

            server2 = HeadlessServer(
                save_file="housetest_tier2.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                success, _time_state, _weather_state = server2.world.load_save_game("housetest_tier2.json")
                self.assertTrue(success)

                house_region = server2.world.get_region(expected_region_id)
                self.assertIsNotNone(house_region)
                self.assertEqual(2, house_region.properties.get("house_tier"))
                self.assertEqual("garden", house_region.properties.get("house_branch"))

                interior = house_region.get_room(house_region.properties.get("interior_room_id"))
                self.assertEqual("Your House (with a Garden)", interior.name)
                self.assertIn("garden plot", interior.description)
            finally:
                server2.shutdown()


class TestPerPlayerHousingSafety(unittest.TestCase):
    """Two players sharing one running world must never collide on a
    single house, region, or key -- the gap this slice closes."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )

    def tearDown(self) -> None:
        self.server.shutdown()

    def _new_owner(self, player_id: str, name: str):
        session = self.server.create_session(player_id=player_id)
        self.server.execute_command(session.session_id, f"char create {name}")
        player = self.server.get_player_for_session(session.session_id)
        player.runtime_state.gold = 1000
        player.current_region_id = "town"
        player.current_room_id = "player_house_exterior"
        return session, player

    def _text(self, session_id: str, command: str) -> str:
        events = self.server.execute_command(session_id, command)
        return "\n".join(str(event["payload"]) for event in events)

    def test_two_players_can_each_own_a_distinct_house(self) -> None:
        session_a, player_a = self._new_owner("house_buyer_a", "Ash")
        session_b, player_b = self._new_owner("house_buyer_b", "Birch")

        self.assertIn("You pay 500 gold", self._text(session_a.session_id, "buy house"))
        self.assertIn("You pay 500 gold", self._text(session_b.session_id, "buy house"))

        house_a = self.server.world.housing_manager.get_owned_house(player_a)
        house_b = self.server.world.housing_manager.get_owned_house(player_b)
        self.assertIsNotNone(house_a)
        self.assertIsNotNone(house_b)
        self.assertNotEqual(house_a.obj_id, house_b.obj_id)

        self._text(session_a.session_id, "in")
        self.assertEqual((house_a.obj_id, "interior"), (player_a.current_region_id, player_a.current_room_id))

        self._text(session_b.session_id, "in")
        self.assertEqual((house_b.obj_id, "interior"), (player_b.current_region_id, player_b.current_room_id))

        key_a = player_a.inventory.find_item_by_id("item_house_key_starter")
        key_b = player_b.inventory.find_item_by_id("item_house_key_starter")
        self.assertNotEqual(key_a.get_property("target_id"), key_b.get_property("target_id"))
        self.assertEqual(house_a.obj_id, key_a.get_property("target_id"))
        self.assertEqual(house_b.obj_id, key_b.get_property("target_id"))

    def test_owning_no_house_gives_a_clear_refusal_not_someone_elses_house(self) -> None:
        owner_session, _owner = self._new_owner("house_owner", "Ash")
        self._text(owner_session.session_id, "buy house")

        visitor_session, visitor = self._new_owner("house_visitor", "Birch")
        visitor.runtime_state.gold = 0

        result = self._text(visitor_session.session_id, "in")
        self.assertIn("don't own a house", result)
        self.assertEqual(("town", "player_house_exterior"), (visitor.current_region_id, visitor.current_room_id))

    def test_replacement_key_lets_owner_back_in_after_losing_the_original(self) -> None:
        session, player = self._new_owner("house_owner_key_loss", "Ash")
        self._text(session.session_id, "buy house")
        self.assertEqual(500, player.runtime_state.gold)

        self._text(session.session_id, "drop house key")
        blocked = self._text(session.session_id, "in")
        self.assertIn("don't have your house key", blocked)
        self.assertEqual(("town", "player_house_exterior"), (player.current_region_id, player.current_room_id))

        replaced = self._text(session.session_id, "replace house key")
        self.assertIn("cuts you a new key", replaced)
        self.assertEqual(400, player.runtime_state.gold)

        house = self.server.world.housing_manager.get_owned_house(player)
        entered = self._text(session.session_id, "in")
        self.assertIn("Your House", entered)
        self.assertEqual((house.obj_id, "interior"), (player.current_region_id, player.current_room_id))
        new_key = player.inventory.find_item_by_id("item_house_key_starter")
        self.assertEqual(house.obj_id, new_key.get_property("target_id"))


class TestHomeStorageAndWorkstation(unittest.TestCase):
    """Persistent home storage (every house) and a workstation utility
    (a tier-2 branch alongside the existing garden/pond flavor branches)."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )

    def tearDown(self) -> None:
        self.server.shutdown()

    def _new_owner(self, player_id: str, name: str):
        session = self.server.create_session(player_id=player_id)
        self.server.execute_command(session.session_id, f"char create {name}")
        player = self.server.get_player_for_session(session.session_id)
        player.runtime_state.gold = 1000
        player.current_region_id = "town"
        player.current_room_id = "player_house_exterior"
        return session, player

    def _text(self, session_id: str, command: str) -> str:
        events = self.server.execute_command(session_id, command)
        return "\n".join(str(event["payload"]) for event in events)

    def test_buying_a_house_provides_working_fixed_storage(self) -> None:
        session, player = self._new_owner("house_owner_storage", "Ash")
        self._text(session.session_id, "buy house")
        self._text(session.session_id, "in")

        self._text(session.session_id, "spawn item_iron_sword")
        self._text(session.session_id, "take iron sword")
        self.assertIn("house storage chest", self._text(session.session_id, "open house storage chest"))

        stored = self._text(session.session_id, "put iron sword in house storage chest")
        self.assertIn("You put the iron sword in the house storage chest", stored)
        self.assertEqual(0, player.inventory.count_item("item_iron_sword"))

        # can_take: false -- it's fixed furniture, not something to carry off.
        take_attempt = self._text(session.session_id, "take house storage chest")
        self.assertIn("fixed in place", take_attempt)

        house = self.server.world.housing_manager.get_owned_house(player)
        room = house.get_room(house.properties.get("interior_room_id"))
        chest = next((item for item in room.items if item.name == "house storage chest"), None)
        self.assertIsNotNone(chest)
        self.assertTrue(
            any(getattr(stored_item, "obj_id", None) == "item_iron_sword" for stored_item in chest.properties.get("contains", []))
        )

    def test_storage_chest_and_its_contents_survive_save_and_a_fresh_server_load(self) -> None:
        with tempfile.TemporaryDirectory() as save_directory:
            server = HeadlessServer(
                save_file="house_storage_test.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                session = server.create_session(player_id="house_owner_storage_persist")
                server.execute_command(session.session_id, "char create Ash")
                player = server.get_player_for_session(session.session_id)
                player.runtime_state.gold = 1000
                player.current_region_id = "town"
                player.current_room_id = "player_house_exterior"
                expected_region_id = f"dynamic_player_house_{player.obj_id}"

                server.execute_command(session.session_id, "buy house")
                server.execute_command(session.session_id, "in")
                server.execute_command(session.session_id, "spawn item_iron_sword")
                server.execute_command(session.session_id, "take iron sword")
                server.execute_command(session.session_id, "open house storage chest")
                server.execute_command(session.session_id, "put iron sword in house storage chest")

                self.assertTrue(server.world.save_game("house_storage_test.json"))
            finally:
                server.shutdown()

            server2 = HeadlessServer(
                save_file="house_storage_test.json",
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                save_directory=save_directory,
                deterministic_test_mode=True,
            )
            try:
                success, _time_state, _weather_state = server2.world.load_save_game("house_storage_test.json")
                self.assertTrue(success)

                house_region = server2.world.get_region(expected_region_id)
                self.assertIsNotNone(house_region)
                room = house_region.get_room(house_region.properties.get("interior_room_id"))
                chest = next((item for item in room.items if item.name == "house storage chest"), None)
                self.assertIsNotNone(chest)
                self.assertFalse(chest.get_property("can_take", True))
                self.assertTrue(
                    any(getattr(stored_item, "obj_id", None) == "item_iron_sword" for stored_item in chest.properties.get("contains", []))
                )
            finally:
                server2.shutdown()

    def test_workstation_branch_places_a_carpentry_bench_and_enables_its_recipe(self) -> None:
        session, player = self._new_owner("house_owner_workstation", "Ash")
        self._text(session.session_id, "buy house")

        for item_id, quantity in (("item_softwood", 6), ("item_iron_ingot", 3)):
            item = ItemFactory.create_item_from_template(item_id, self.server.world)
            player.inventory.add_item(item, quantity)

        expanded = self._text(session.session_id, "expand house workstation")
        self.assertIn("Home Workshop", expanded)
        self.assertEqual(250, player.runtime_state.gold)

        self._text(session.session_id, "in")

        house = self.server.world.housing_manager.get_owned_house(player)
        room = house.get_room(house.properties.get("interior_room_id"))
        self.assertTrue(any(item.get_property("crafting_station_type") == "carpentry_bench" for item in room.items))

        for item_id, quantity in (("item_softwood", 4), ("item_iron_ingot", 1)):
            item = ItemFactory.create_item_from_template(item_id, self.server.world)
            player.inventory.add_item(item, quantity)

        crafted = self._text(session.session_id, "craft build_wooden_toolbox")
        self.assertIn("Successfully crafted", crafted)
        self.assertEqual(1, player.inventory.count_item("item_wooden_toolbox"))


if __name__ == "__main__":
    unittest.main()
