# tests/singles/test_mercantile_commands.py
"""Coverage for engine/commands/mercantile.py beyond what
test_economy_*.py/test_vendor_*.py already exercise: discount display,
static sells_items catalog edge cases, and trade/list/buy/sell/stoptrade/
repair guard branches.

Note: three branches are provably unreachable and left untested, consistent
with this codebase's established precedent for dead code:
- sell_handler's `if removed_item_type:` before granting gold -- the
  preceding `if not removed_item_type or ...: return` already guarantees
  removed_item_type is truthy by the time this line runs.
- repair_handler's and repaircost_handler's `if repair_cost is None:
  return ...` -- _calculate_repair_cost only ever returns a None cost
  together with a truthy error message, and the preceding `if error_msg:
  return ...` already handles that case first."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.commands.mercantile import (
    trade_handler, list_handler, buy_handler, sell_handler,
    stoptrade_handler, repair_handler, repaircost_handler,
)


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

    def test_no_player_reports_start_or_load(self):
        result = trade_handler(["someone"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

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

    def test_no_player_reports_start_or_load(self):
        result = list_handler([], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_sells_items_entry_missing_item_id_is_skipped(self):
        vendor = self._make_vendor(sells_items=[
            {"price_multiplier": 1.0},  # no item_id at all
            {"item_id": "item_starter_dagger", "price_multiplier": 1.0},
        ])
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("list")
        self.assertIn("Wares", result)

    def test_sells_items_entry_with_unknown_template_is_skipped(self):
        vendor = self._make_vendor(sells_items=[
            {"item_id": "totally_bogus_item_template_xyz"},
            {"item_id": "item_starter_dagger", "price_multiplier": 1.0},
        ])
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("list")
        self.assertNotIn("bogus", result)

    def test_dynamic_stock_items_are_listed(self):
        vendor = self._make_vendor()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        vendor.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("list")
        self.assertIn(sword.name, result)


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

    def test_catalog_scan_skips_missing_id_and_unknown_template_before_match(self):
        vendor = self._make_vendor(sells_items=[
            {"price_multiplier": 1.0},  # no item_id
            {"item_id": "totally_bogus_item_xyz"},  # unknown template
            {"item_id": "item_starter_dagger", "price_multiplier": 1.0},
        ])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        result = self.game.process_command("buy item_starter_dagger")
        self.assertIn("You buy", result)

    def test_dynamic_stock_insufficient_gold_is_reported(self):
        vendor = self._make_vendor()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        vendor.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 0
        result = self.game.process_command(f"buy {sword.name}")
        self.assertIn("enough gold", result)

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

    def test_no_player_reports_start_or_load(self):
        result = buy_handler(["sword"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_unicode_digit_quantity_raises_value_error(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        # '²' (superscript two) passes str.isdigit() but int() rejects it.
        result = self.game.process_command("buy dagger ²")
        self.assertIn("Invalid quantity", result)

    def test_digits_only_args_leaves_no_item_name(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("buy 5")
        self.assertIn("must specify an item name", result)

    def test_dynamic_stock_insufficient_quantity_is_reported(self):
        vendor = self._make_vendor()
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        vendor.inventory.add_item(potion, 1)
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        result = self.game.process_command("buy small healing potion 5")
        self.assertIn("only has", result)

    def test_dynamic_stock_insufficient_inventory_space_is_reported(self):
        vendor = self._make_vendor()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        vendor.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        with patch.object(self.player.inventory, "can_add_item", return_value=(False, "no room")):
            result = self.game.process_command(f"buy {sword.name}")
        self.assertIn("no room", result)

    def test_dynamic_stock_removal_failure_still_reports_success(self):
        vendor = self._make_vendor()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        vendor.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        with patch.object(vendor.inventory, "remove_item", return_value=(None, 0, "mock failure")):
            result = self.game.process_command(f"buy {sword.name}")
        self.assertIn("You buy", result)

    def test_dynamic_stock_stackable_item_is_recreated_per_unit(self):
        vendor = self._make_vendor()
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        vendor.inventory.add_item(potion, 3)
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        result = self.game.process_command("buy small healing potion 3")
        self.assertIn("You buy 3", result)
        self.assertEqual(3, self.player.inventory.count_item("item_healing_potion_small"))

    def test_static_catalog_factory_failure_reports_internal_error(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        with patch("engine.commands.mercantile.ItemFactory.create_item_from_template", return_value=None):
            result = self.game.process_command("buy dagger")
        self.assertIn("Internal error", result)

    def test_static_catalog_purchase_loop_add_failure_reverts_gold(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        starting_gold = self.player.runtime_state.gold
        with patch.object(self.player.inventory, "can_add_item", return_value=(True, "")):
            with patch.object(self.player.inventory, "add_item", return_value=(False, "no room")):
                result = self.game.process_command("buy dagger 2")
        self.assertIn("partially reverted", result)
        self.assertEqual(self.player.runtime_state.gold, starting_gold)

    def test_static_catalog_purchase_loop_instance_creation_failure_reverts_gold(self):
        vendor = self._make_vendor(sells_items=[{"item_id": "item_starter_dagger"}])
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        starting_gold = self.player.runtime_state.gold
        real_create = ItemFactory.create_item_from_template
        # Succeed once (for the pre-flight can_add_item probe via temp_item),
        # then fail on every call inside the purchase loop.
        with patch(
            "engine.commands.mercantile.ItemFactory.create_item_from_template",
            side_effect=[real_create("item_starter_dagger", self.world), None],
        ):
            result = self.game.process_command("buy dagger")
        self.assertIn("Transaction cancelled", result)
        self.assertEqual(self.player.runtime_state.gold, starting_gold)


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

    def test_no_player_reports_start_or_load(self):
        result = sell_handler(["sword"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_unicode_digit_quantity_raises_value_error(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("sell sword ²")
        self.assertIn("Invalid quantity", result)

    def test_digits_only_args_leaves_no_item_name(self):
        vendor = self._make_vendor()
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command("sell 5")
        self.assertIn("must specify an item name", result)

    def test_insufficient_owned_quantity_is_reported(self):
        vendor = self._make_vendor(buys_item_types=["Weapon"])
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        result = self.game.process_command(f"sell {sword.name} 5")
        self.assertIn("only have", result)

    def test_removal_mismatch_cancels_sale(self):
        vendor = self._make_vendor(buys_item_types=["Weapon"])
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(sword)
        self.player.trading_with = vendor.obj_id
        with patch.object(self.player.inventory, "remove_item", return_value=(sword, 0, "mismatch")):
            result = self.game.process_command(f"sell {sword.name}")
        self.assertIn("Sale cancelled", result)


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

    def test_no_player_reports_start_or_load(self):
        result = stoptrade_handler([], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)


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

    def test_repair_no_player_reports_start_or_load(self):
        result = repair_handler(["sword"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_dead_player_cannot_repair(self):
        self.player.health = 0
        self.player.is_alive = False
        result = repair_handler(["sword"], {"world": self.world, "player": self.player})
        self.assertIn("dead", result)

    def test_repair_inventory_item_without_durability_reports_no_durability(self):
        self._make_repairer()
        gem = ItemFactory.create_item_from_template("item_ruby", self.world)
        self.player.inventory.add_item(gem)
        result = self.game.process_command(f"repair {gem.name}")
        self.assertIn("doesn't have durability", result)

    def test_equipped_item_with_durability_is_found_and_repaired(self):
        self._make_repairer()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword.get_property("durability") is not None:
            sword.update_property("durability", 1)
            self.player.equipment["main_hand"] = sword
            self.player.runtime_state.gold = 1000
            result = self.game.process_command(f"repair {sword.name}")
            self.assertIn("perfect condition", result)

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

    def test_repaircost_no_player_reports_start_or_load(self):
        result = repaircost_handler(["sword"], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_equipped_item_without_durability_cannot_be_repaired(self):
        self._make_repairer()
        gem = ItemFactory.create_item_from_template("item_ruby", self.world)
        self.player.equipment["main_hand"] = gem
        result = self.game.process_command(f"repaircost {gem.name}")
        self.assertIn("cannot be repaired", result)

    def test_equipped_item_with_durability_is_found(self):
        self._make_repairer()
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword.get_property("durability") is not None:
            sword.update_property("durability", 1)
            self.player.equipment["main_hand"] = sword
            result = self.game.process_command(f"repaircost {sword.name}")
            self.assertIn("quotes a price", result)

    def test_item_not_found_after_equipment_scan_is_reported(self):
        self._make_repairer()
        result = self.game.process_command("repaircost totally_bogus_item_xyz")
        self.assertIn("don't have an item called", result)

    def test_repaircost_inventory_item_without_durability_reports_no_durability(self):
        self._make_repairer()
        gem = ItemFactory.create_item_from_template("item_ruby", self.world)
        self.player.inventory.add_item(gem)
        result = self.game.process_command(f"repaircost {gem.name}")
        self.assertIn("doesn't have durability", result)
