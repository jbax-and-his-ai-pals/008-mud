# tests/singles/test_inventory_remove_nonexistent.py
from tests.fixtures import GameTestBase

class TestInventoryRemoveNonexistent(GameTestBase):

    def test_remove_missing_item(self):
        """Verify removing an item ID that doesn't exist fails gracefully."""
        # Ensure empty
        self.player.inventory.slots = []
        
        # Act
        item, count, msg = self.player.inventory.remove_item("ghost_item", 1)
        
        # Assert
        self.assertIsNone(item)
        self.assertEqual(count, 0)
        self.assertIn("don't have", msg)