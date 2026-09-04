# tests/singles/test_stacking_advanced.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestStackingAdvanced(GameTestBase):

    def test_partial_stack_removal(self):
        """Verify removing part of a stack correctly updates quantity and weight."""
        # 1. Setup Stackable Item (Potions weigh 0.5)
        self.world.item_templates["stack_item"] = {
            "type": "Consumable", "name": "Stackable", "value": 10, "weight": 0.5,
            "stackable": True
        }
        item = ItemFactory.create_item_from_template("stack_item", self.world)
        
        if item:
            # Add 10 items (Total weight 5.0)
            self.player.inventory.add_item(item, 10)
            self.assertEqual(self.player.inventory.count_item("stack_item"), 10)
            self.assertAlmostEqual(self.player.inventory.get_total_weight(), 5.0)
            
            # 2. Remove 4 items
            removed_item, removed_qty, _ = self.player.inventory.remove_item("stack_item", 4)
            
            # 3. Assertions
            self.assertEqual(removed_qty, 4)
            self.assertEqual(self.player.inventory.count_item("stack_item"), 6)
            # 6 * 0.5 = 3.0
            self.assertAlmostEqual(self.player.inventory.get_total_weight(), 3.0)

    def test_remove_more_than_available(self):
        """Verify removal caps at the total available quantity."""
        item = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        if item:
            self.player.inventory.add_item(item, 5)
            
            # Try to remove 10
            _, actual_removed, _ = self.player.inventory.remove_item(item.obj_id, 10)
            
            self.assertEqual(actual_removed, 5)
            self.assertEqual(self.player.inventory.count_item(item.obj_id), 0)