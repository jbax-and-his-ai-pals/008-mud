# tests/singles/test_take_all_fixed_items.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestTakeAllFixedItems(GameTestBase):

    def test_take_all_skips_fixed_items(self):
        """Verify 'take all' does not pick up items marked can_take=False."""
        # 1. Setup Room
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.world)
        self.world.item_templates["heavy_anvil"] = {
            "type": "Item", "name": "Heavy Anvil", 
            "properties": {"can_take": False}
        }
        anvil = ItemFactory.create_item_from_template("heavy_anvil", self.world)
        
        # Ensure items created and player location is valid
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        
        if coin and anvil and rid and room_id:
            self.world.add_item_to_room(rid, room_id, coin)
            self.world.add_item_to_room(rid, room_id, anvil)
            
            # 2. Act
            result = self.game.process_command("take all")
            
            # 3. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("Heavy Anvil", result)
                self.assertTrue("too heavy" in result.lower() or "fixed" in result.lower())
            
            # Check Inventory
            self.assertEqual(self.player.inventory.count_item("item_gold_coin"), 1)
            self.assertEqual(self.player.inventory.count_item("heavy_anvil"), 0)
            
            # Check Room
            room_items = self.world.get_items_in_current_room()
            self.assertIn(anvil, room_items)
            self.assertNotIn(coin, room_items)
        else:
            self.fail("Setup failed: Items or Player location invalid.")