# tests/singles/test_inventory_stack_split_limits.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventoryStackSplitLimits(GameTestBase):

    def setUp(self):
        super().setUp()
        self.world.item_templates["coin"] = {
            "type": "Treasure", "name": "Coin", "stackable": True, "weight": 0.1
        }

    def test_split_more_than_owned(self):
        """Verify dropping more items than in stack clamps to max available."""
        item = ItemFactory.create_item_from_template("coin", self.world)
        if item:
            self.player.inventory.add_item(item, 5)
            
            # Act: Drop 10
            _, count, _ = self.player.inventory.remove_item(item.obj_id, 10)
            
            # Assert
            self.assertEqual(count, 5, "Should only remove 5.")
            self.assertEqual(self.player.inventory.count_item(item.obj_id), 0)

    def test_split_exact_amount(self):
        """Verify dropping exact stack amount clears the slot."""
        item = ItemFactory.create_item_from_template("coin", self.world)
        if item:
            self.player.inventory.add_item(item, 5)
            
            _, count, _ = self.player.inventory.remove_item(item.obj_id, 5)
            
            self.assertEqual(count, 5)
            self.assertEqual(self.player.inventory.count_item(item.obj_id), 0)