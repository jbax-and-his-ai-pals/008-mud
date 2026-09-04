# tests/singles/test_mercantile_commands.py
"""Coverage for engine/commands/mercantile.py beyond what
test_economy_*.py/test_vendor_*.py already exercise: discount display,
static sells_items catalog edge cases, and trade/list/buy/sell/stoptrade/
repair guard branches."""

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


class _VendorTestBase(GameTestBase):
    def _make_vendor(self, template_id="greedy_merchant", **props):
        self.world.npc_templates[template_id] = {
            "name": "Merchant", "faction": "friendly",
            "properties": {"is_vendor": True, **props},
        }
        vendor = NPCFactory.create_npc_from_template(template_id, self.world)
        self.world.add_npc(vendor)
        vendor.current_region_id = self.player.current_region_id
        vendor.current_room_id = self.player.current_room_id
        return vendor


class TestTradeCommand(_VendorTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("trade")
        self.assertIn("Trade with whom", result)

    def test_dead_player_cannot_trade(self):
        from engine.commands.mercantile import trade_handler
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = trade_handler(["merchant"], context)
        self.assertIn("cannot trade while dead", result)

    def test_npc_not_found(self):
        result = self.game.process_command("trade nobody_here")
        self.assertIn("don't see", result)

    def test_npc_not_a_vendor(self):
        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="not_vendor")
        elder.current_region_id = self.player.current_region_id
        elder.current_room_id = self.player.current_room_id
        self.world.add_npc(elder)
        result = self.game.process_command(f"trade {elder.name}")
        self.assertIn("doesn't seem interested", result)

    def test_starting_a_new_trade_ends_the_previous_one(self):
        vendor1 = self._make_vendor("vendor_one")
        self.world.npc_templates["vendor_two"] = {
            "name": "Other Merchant", "faction": "friendly", "properties": {"is_vendor": True},
        }
        vendor2 = NPCFactory.create_npc_from_template("vendor_two", self.world)
        self.world.add_npc(vendor2)
        vendor2.current_region_id = self.player.current_region_id
        vendor2.current_room_id = self.player.current_room_id

        self.player.trading_with = vendor1.obj_id
        vendor1.is_trading = True

        self.game.process_command(f"trade {vendor2.name}")
        self.assertFalse(vendor1.is_trading)
        self.assertEqual(vendor2.obj_id, self.player.trading_with)


class TestListCommand(_VendorTestBase):
    def test_not_trading_is_reported(self):
        result = self.game.process_command("list")
        self.assertIn("not currently trading", result)

    def test_vendor_no_longer_present_clears_trading_state(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        vendor.current_room_id = "somewhere_else"
        result = self.game.process_command("list")
        self.assertIn("no longer here", result)
        self.assertIsNone(self.player.trading_with)

    def test_discount_is_displayed_when_active(self):
        vendor = self._make_vendor(
            sells_items=[{"item_id": "item_starter_dagger", "price_multiplier": 2.0}],
            economy_impact={"discount": 0.5},
        )
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("list")
        self.assertIn("Special Discount Active", result)

    def test_nothing_to_sell_is_reported(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("list")
        self.assertIn("nothing to sell", result)


class TestBuyCommand(_VendorTestBase):
    def test_not_trading_is_reported(self):
        result = self.game.process_command("buy sword")
        self.assertIn("trade' with someone first", result)

    def test_vendor_gone_is_reported(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        vendor.current_room_id = "elsewhere"
        result = self.game.process_command("buy sword")
        self.assertIn("gone", result)

    def test_no_item_name_shows_usage(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("buy")
        self.assertIn("Buy what", result)

    def test_zero_quantity_is_rejected(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("buy dagger 0")
        self.assertIn("must be positive", result)

    def test_unsold_item_is_reported(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("buy not_a_real_item")
        self.assertIn("doesn't sell", result)

    def test_static_catalog_purchase_with_insufficient_gold(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger", "price_multiplier": 5.0}])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 0
        result = self.game.process_command("buy item_starter_dagger")
        self.assertIn("enough gold", result)

    def test_static_catalog_purchase_of_multiple_quantity(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_healing_potion_small", "price_multiplier": 1.0}])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        result = self.game.process_command("buy item_healing_potion_small 3")
        self.assertIn("You buy 3", result)
        self.assertEqual(3, self.player.inventory.count_item("item_healing_potion_small"))


class TestSellCommand(_VendorTestBase):
    def test_not_trading_is_reported(self):
        result = self.game.process_command("sell sword")
        self.assertIn("trade' with someone first", result)

    def test_vendor_gone_is_reported(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        vendor.current_room_id = "elsewhere"
        result = self.game.process_command("sell sword")
        self.assertIn("gone", result)

    def test_no_item_name_shows_usage(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("sell")
        self.assertIn("Sell what", result)

    def test_zero_quantity_is_rejected(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("sell sword 0")
        self.assertIn("must be positive", result)

    def test_item_not_owned_is_reported(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("sell not_an_item_i_have")
        self.assertIn("don't have", result)


class TestStoptradeCommand(_VendorTestBase):
    def test_not_trading_is_reported(self):
        result = self.game.process_command("stoptrade")
        self.assertEqual("You are not currently trading with anyone.", result)

    def test_stops_trading(self):
        vendor = self._make_vendor()
        self.game.process_command(f"trade {vendor.name}")
        result = self.game.process_command("stoptrade")
        self.assertIn("stop trading", result)
        self.assertIsNone(self.player.trading_with)
        self.assertFalse(vendor.is_trading)


class TestRepairAndRepaircost(_VendorTestBase):
    def _make_repairer(self):
        return self._make_vendor("repairer", can_repair=True, is_vendor=False)

    def test_repair_no_args_shows_usage(self):
        result = self.game.process_command("repair")
        self.assertIn("What item", result)

    def test_repair_no_repairer_present(self):
        result = self.game.process_command("repair sword")
        self.assertIn("no one here", result)

    def test_repair_item_not_found(self):
        self._make_repairer()
        result = self.game.process_command("repair not_an_item")
        self.assertIn("don't have an item called", result)

    def test_repair_equipped_item_without_durability_cannot_be_repaired(self):
        # Only equipped (not in inventory), so repair_handler must fall
        # through to its equipment-slot scan to find it.
        from engine.items.item_factory import ItemFactory
        self._make_repairer()
        gem = ItemFactory.create_item_from_template("item_ruby", self.world)
        self.player.equipment["main_hand"] = gem  # no durability property
        result = self.game.process_command(f"repair {gem.name}")
        self.assertIn("cannot be repaired", result)

    def test_repaircost_no_args_shows_usage(self):
        result = self.game.process_command("repaircost")
        self.assertIn("What item", result)

    def test_repaircost_no_repairer_present(self):
        result = self.game.process_command("repaircost sword")
        self.assertIn("no one here", result)

    def test_repaircost_undamaged_item_needs_no_repair(self):
        from engine.items.item_factory import ItemFactory
        self._make_repairer()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword.get_property("durability") is not None:
            sword.update_property("durability", sword.get_property("max_durability"))
            self.player.inventory.add_item(sword)
            result = self.game.process_command(f"repaircost {sword.name}")
            self.assertIn("does not need repairing", result)
