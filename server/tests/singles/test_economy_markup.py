# tests/singles/test_economy_markup.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestEconomyMarkup(GameTestBase):

    def test_buy_price_calculation(self):
        """Verify items sold by vendors respect price_multiplier."""
        # 1. Setup Item Template FIRST (so the vendor template refers to something valid)
        self.world.item_templates["test_ware"] = {"type": "Item", "name": "Ware", "value": 10}

        # 2. Setup Vendor Template with specific markup
        self.world.npc_templates["greedy_merchant"] = {
            "name": "Greedy", "faction": "friendly",
            "properties": {
                "is_vendor": True,
                "sells_items": [
                    # Base Value 10 * 2.5 multiplier = 25g
                    {"item_id": "test_ware", "price_multiplier": 2.5}
                ]
            }
        }
        
        # 3. Create Vendor
        vendor = NPCFactory.create_npc_from_template("greedy_merchant", self.world)
        self.assertIsNotNone(vendor, "Failed to create greedy merchant.")
        
        if vendor:
            self.world.add_npc(vendor)
            
            # Ensure Colocation
            vendor.current_region_id = self.player.current_region_id
            vendor.current_room_id = self.player.current_room_id
            
            # 4. Initiate Trade
            self.player.trading_with = vendor.obj_id
            
            # 5. Check Listing
            result = self.game.process_command("list")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("25 gold", result, "Price multiplier not applied correctly in list.")
            
            # 6. Verify Factory can produce the item (Sanity check)
            test_item = ItemFactory.create_item_from_template("test_ware", self.world)
            self.assertIsNotNone(test_item, "Factory failed to create the test item.")

            # 7. Attempt Buy with exact change
            self.player.runtime_state.gold = 25
            res_buy = self.game.process_command("buy Ware")
            
            # 8. Assertions
            self.assertIsNotNone(res_buy)
            if res_buy:
                self.assertIn("You buy", res_buy)
            
            self.assertEqual(self.player.runtime_state.gold, 0, "Gold was not deducted correctly.")
            self.assertEqual(self.player.inventory.count_item("test_ware"), 1, "Item was not added to inventory.")
