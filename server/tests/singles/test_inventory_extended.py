# tests/singles/test_inventory_extended.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventoryExtended(GameTestBase):
    
    def test_encumbrance_limit(self):
        """Verify items cannot be added if weight limit is exceeded."""
        # Setup: Low capacity
        self.player.inventory.max_weight = 10.0
        
        # Create heavy item (Weight 200)
        anvil = ItemFactory.create_item_from_template("item_anvil", self.world)
        self.assertIsNotNone(anvil)
        
        if anvil:
            # Act
            success, msg = self.player.inventory.add_item(anvil)
            
            # Assert
            self.assertFalse(success)
            self.assertIn("exceed", msg)
            self.assertEqual(self.player.inventory.count_item(anvil.obj_id), 0)

    def test_stack_merging(self):
        """Verify stackable items merge into a single slot."""
        potion1 = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        potion2 = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        
        if potion1 and potion2:
            self.player.inventory.add_item(potion1)
            self.player.inventory.add_item(potion2)
            
            # Assert
            # Should occupy 1 slot, not 2
            occupied_slots = [s for s in self.player.inventory.slots if s.item]
            self.assertEqual(len(occupied_slots), 1)
            
            # Quantity should be 2
            self.assertEqual(occupied_slots[0].quantity, 2)

    def test_stack_splitting(self):
        """Verify removing part of a stack leaves the rest."""
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        
        if potion:
            # Add 10 potions
            self.player.inventory.add_item(potion, 10)
            self.assertEqual(self.player.inventory.count_item(potion.obj_id), 10)
            
            # Remove 3
            removed_item, count, _ = self.player.inventory.remove_item(potion.obj_id, 3)
            
            # Assert removal
            self.assertIsNotNone(removed_item)
            self.assertEqual(count, 3)
            
            # Assert remainder
            self.assertEqual(self.player.inventory.count_item(potion.obj_id), 7)
            # Should still be in inventory
            self.assertIsNotNone(self.player.inventory.find_item_by_id(potion.obj_id))