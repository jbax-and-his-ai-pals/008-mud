# tests/singles/test_inventory_weight_limit.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventoryWeightLimit(GameTestBase):

    def test_weight_cap_enforcement(self):
        """Verify items cannot be added if weight limit is exceeded."""
        # 1. Constrain Weight
        self.player.inventory.max_weight = 10.0
        
        # 2. Add Heavy Item (9.0)
        self.world.item_templates["heavy_rock"] = {"type": "Item", "name": "Rock", "weight": 9.0}
        rock1 = ItemFactory.create_item_from_template("heavy_rock", self.world)
        if rock1: self.player.inventory.add_item(rock1)
        
        self.assertEqual(self.player.inventory.get_total_weight(), 9.0)
        
        # 3. Attempt Add Second Heavy Item (9.0) -> Total 18.0 > 10.0
        rock2 = ItemFactory.create_item_from_template("heavy_rock", self.world)
        
        self.assertIsNotNone(rock2, "Failed to create rock2")
        
        if rock2:
            # Act
            success, msg = self.player.inventory.add_item(rock2)
            
            # Assert
            self.assertFalse(success)
            self.assertIn("exceed", msg)
            self.assertEqual(self.player.inventory.count_item("heavy_rock"), 1)