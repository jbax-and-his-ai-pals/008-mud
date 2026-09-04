# tests/singles/test_inventory_stack_slot_conservation.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventoryStackSlotConservation(GameTestBase):

    def test_adding_stackable_uses_existing_slot(self):
        """Verify adding more of an existing item doesn't consume a new slot."""
        # 1. Setup: 1 Slot inventory
        self.player.inventory.max_slots = 1
        self.player.inventory.slots = [self.player.inventory.slots[0]]
        
        # 2. Add first Coin
        # FIX: Use 'Item' instead of 'Treasure', as Treasure class enforces stackable=False in its init
        self.world.item_templates["coin"] = {"type": "Item", "name": "Coin", "value": 1, "stackable": True}
        c1 = ItemFactory.create_item_from_template("coin", self.world)
        
        if c1:
            self.player.inventory.add_item(c1)
            self.assertEqual(self.player.inventory.get_empty_slots(), 0)
            
            # 3. Add second Coin
            c2 = ItemFactory.create_item_from_template("coin", self.world)
            if c2:
                success, msg = self.player.inventory.add_item(c2)
                
                # 4. Assert
                self.assertTrue(success, f"Should succeed by stacking. Error: {msg}")
                self.assertEqual(self.player.inventory.count_item("coin"), 2)
                self.assertEqual(len([s for s in self.player.inventory.slots if s.item]), 1)