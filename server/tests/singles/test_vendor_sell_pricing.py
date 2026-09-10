"""Coverage for the general-store economy overhaul in
engine/commands/mercantile.py's sell_handler: per-vendor sell rates,
weight-based pricing for a still-locked container, and the quest-item
sale exclusion."""

import tempfile
import unittest

from tests.fixtures import FANTASY_FRONTIER
from engine.items.chest_loot_generator import ChestLootGenerator
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer


def _make_server(save_file: str, save_directory: str) -> HeadlessServer:
    return HeadlessServer(
        save_file=save_file, db_path=":memory:",
        content_set_path=str(FANTASY_FRONTIER), save_directory=save_directory,
        deterministic_test_mode=True,
    )


class TestVendorSellPricingCases(unittest.TestCase):
    def setUp(self):
        self._tmpdir_ctx = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir_ctx.name
        self.server = _make_server("sell_pricing_test.json", self.tmpdir)
        self.session = self.server.create_session(player_id="seller")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self):
        self.server.shutdown()
        self._tmpdir_ctx.cleanup()

    def _text(self, events):
        return "\n".join(str(event["payload"]) for event in events)

    def test_ordinary_vendor_keeps_the_default_sell_rate(self):
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.server.world)
        self.player.inventory.add_item(sword, 1)
        self.player.current_region_id = "town"
        self.player.current_room_id = "blacksmith_interior"
        self.server.execute_command(self.session.session_id, "trade Grenda")

        result = self._text(self.server.execute_command(self.session.session_id, "sell iron sword"))
        self.assertIn(f"for {int(sword.value * 0.4)} gold", result)

    def test_general_store_pays_less_than_the_default_rate(self):
        # Talia's buys_item_types doesn't include Weapon (that's the
        # blacksmith's specialty) -- use a Treasure item, which she already
        # accepts and which has enough value for the two rates to differ.
        treasure = ItemFactory.create_item_from_template("item_gold_nugget", self.server.world)
        value = treasure.value
        self.player.inventory.add_item(treasure, 1)
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        self.server.execute_command(self.session.session_id, "trade Talia")

        result = self._text(self.server.execute_command(self.session.session_id, "sell gold nugget"))
        self.assertIn(f"for {int(value * 0.2)} gold", result)
        self.assertLess(int(value * 0.2), int(value * 0.4))

    def test_locked_chest_sells_by_weight_not_value(self):
        chest = ChestLootGenerator.generate_chest(self.server.world, level=10)
        self.assertTrue(chest.properties.get("locked"))
        expected_price = max(0, int(chest.weight * 1.5))

        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        self.server.world.add_item_to_room("town", "market_square", chest)
        self.server.execute_command(self.session.session_id, f"take {chest.name}")
        self.server.execute_command(self.session.session_id, "trade Talia")

        result = self._text(self.server.execute_command(self.session.session_id, f"sell {chest.name}"))
        self.assertIn(f"for {expected_price} gold", result)

    def test_unlocked_chest_falls_back_to_value_based_pricing(self):
        chest = ChestLootGenerator.generate_chest(self.server.world, level=1)
        chest.properties["locked"] = False
        expected_price = max(0, int(chest.value * 0.2))

        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        self.server.world.add_item_to_room("town", "market_square", chest)
        self.server.execute_command(self.session.session_id, f"take {chest.name}")
        self.server.execute_command(self.session.session_id, "trade Talia")

        result = self._text(self.server.execute_command(self.session.session_id, f"sell {chest.name}"))
        self.assertIn(f"for {expected_price} gold", result)

    def test_quest_item_cannot_be_sold_to_any_vendor(self):
        package = ItemFactory.create_item_from_template("quest_package_generic", self.server.world)
        self.assertTrue(package.get_property("quest_item"))
        self.player.inventory.add_item(package, 1)
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        self.server.execute_command(self.session.session_id, "trade Talia")
        gold_before = self.player.runtime_state.gold

        result = self._text(self.server.execute_command(self.session.session_id, "sell Sealed Package"))
        self.assertIn("isn't something you can part with", result)
        self.assertEqual(gold_before, self.player.runtime_state.gold)
        self.assertEqual(1, self.player.inventory.count_item("quest_package_generic"))


if __name__ == "__main__":
    unittest.main()
