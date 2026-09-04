# tests/singles/test_vendor_partial_stack.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestVendorPartialStack(GameTestBase):

    def test_sell_split_stack(self):
        """Verify selling 5 of 10 items works and calculates gold correctly."""
        # 1. Setup Vendor
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant:
             merchant = NPCFactory.create_npc_from_template("wandering_villager", self.world)
             if merchant:
                 merchant.properties["is_vendor"] = True
                 merchant.properties["buys_item_types"] = ["Item", "Gem"] # Ensure they buy our test type
        
        self.assertIsNotNone(merchant, "Failed to create merchant.")
        
        if merchant:
            self.world.add_npc(merchant)
            merchant.current_region_id = self.player.current_region_id
            merchant.current_room_id = self.player.current_room_id
            
            # 2. Setup Inventory (10 Test Gems, Value 100 each)
            # Use basic "Item" type to avoid subclass dependency issues in tests, enforce stackable
            self.world.item_templates["test_gem"] = {
                "type": "Item", "name": "Test Gem", "value": 100, "stackable": True
            }
            
            gem = ItemFactory.create_item_from_template("test_gem", self.world)
            self.assertIsNotNone(gem, "Failed to create Test Gem item.")
            
            if gem: 
                # Add 10
                added, msg = self.player.inventory.add_item(gem, 10)
                self.assertTrue(added, f"Failed to add gems: {msg}")
                self.assertEqual(self.player.inventory.count_item("test_gem"), 10)
            
            self.player.runtime_state.gold = 0
            self.player.trading_with = merchant.obj_id
            
            # 3. Act: Sell 5
            # Value 100 * 0.4 (default buy mult) = 40g per item.
            # 5 * 40 = 200g.
            result = self.game.process_command("sell Test Gem 5")
            
            self.assertIsNotNone(result)
            if result:
                 self.assertIn("You sell", result)
            
            # 4. Assert
            self.assertEqual(self.player.inventory.count_item("test_gem"), 5)
            self.assertEqual(self.player.runtime_state.gold, 200)
