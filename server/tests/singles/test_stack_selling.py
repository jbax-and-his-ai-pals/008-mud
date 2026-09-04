# tests/singles/test_stack_selling.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestStackSelling(GameTestBase):

    def test_sell_partial_stack(self):
        """Verify selling a portion of a stack calculates gold correctly."""
        # 1. Setup Vendor
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if merchant:
            self.world.add_npc(merchant)
            merchant.current_region_id = self.player.current_region_id
            merchant.current_room_id = self.player.current_room_id
            
            # 2. Setup Player Items
            # Create stackable item worth 10 gold
            self.world.item_templates["gold_bar"] = {
                "type": "Treasure", "name": "Gold Bar", "value": 10, "stackable": True
            }
            bar = ItemFactory.create_item_from_template("gold_bar", self.world)
            if bar:
                self.player.inventory.add_item(bar, 10) # 10 bars
                
            self.player.runtime_state.gold = 0
            self.player.trading_with = merchant.obj_id
            
            # 3. Act: Sell 4 bars
            # Value = 10. Multiplier usually 0.4 -> 4 gold per item.
            # Total = 4 * 4 = 16 gold.
            self.game.process_command("sell Gold Bar 4")
            
            # 4. Assert
            self.assertEqual(self.player.inventory.count_item("gold_bar"), 6, "Should have 6 bars left.")
            
            expected_price_per = int(10 * 0.4) # 4
            expected_total = expected_price_per * 4 # 16
            
            self.assertEqual(self.player.runtime_state.gold, expected_total, "Gold calculation incorrect.")
