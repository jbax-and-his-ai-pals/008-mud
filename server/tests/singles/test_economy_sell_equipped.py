# tests/singles/test_economy_sell_equipped.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestEconomySellEquipped(GameTestBase):

    def test_sell_equipped_item_fails(self):
        """Verify players cannot sell an item while it is currently equipped."""
        # 1. Setup Vendor
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        self.assertIsNotNone(merchant, "Failed to create merchant.")
        
        if merchant:
            self.world.add_npc(merchant)
            merchant.current_region_id = self.player.current_region_id
            merchant.current_room_id = self.player.current_room_id
            
            # 2. Setup Item
            sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            self.assertIsNotNone(sword, "Failed to create sword.")
            
            if sword:
                self.player.inventory.add_item(sword)
                self.player.equip_item(sword, "main_hand")
                
                self.assertTrue(self.player.equipment["main_hand"] == sword)
                
                # 3. Act: Try to sell
                self.player.trading_with = merchant.obj_id
                result = self.game.process_command("sell iron sword")
                
                # 4. Assert
                self.assertIsNotNone(result)
                if result:
                    self.assertIn("don't have", result.lower())
                
                # Verify still equipped
                self.assertEqual(self.player.equipment["main_hand"], sword)