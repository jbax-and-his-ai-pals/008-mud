# tests/singles/test_inventory_max_slots.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventoryMaxSlots(GameTestBase):

    def test_slot_limit_enforcement(self):
        """Verify items cannot be added if slots are full."""
        # 1. Constrain Inventory
        self.player.inventory.max_slots = 2
        self.player.inventory.slots = self.player.inventory.slots[:2] # Resize list
        self.player.inventory.max_weight = 1000.0 # High weight limit
        
        # 2. Fill Slots with unique items (non-stackable)
        i1 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        i2 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        
        self.assertIsNotNone(i1, "Failed to create item 1")
        self.assertIsNotNone(i2, "Failed to create item 2")
        
        if i1 and i2:
            i1.obj_id = "s1"; i2.obj_id = "s2" # Ensure unique
            
            self.player.inventory.add_item(i1)
            self.player.inventory.add_item(i2)
            
            self.assertEqual(self.player.inventory.get_empty_slots(), 0)
            
            # 3. Attempt Add 3rd Item
            i3 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            self.assertIsNotNone(i3, "Failed to create item 3")
            
            if i3:
                success, msg = self.player.inventory.add_item(i3)
                
                # 4. Assert Failure
                self.assertFalse(success)
                self.assertIn("empty inventory slots", msg)