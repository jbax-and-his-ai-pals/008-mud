# tests/singles/test_inventory_slot_limit.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventorySlotLimit(GameTestBase):

    def test_slot_capacity_enforcement(self):
        """Verify items are rejected when all slots are full."""
        # Setup: 2 slots max
        self.player.inventory.max_slots = 2
        self.player.inventory.slots = [self.player.inventory.slots[0], self.player.inventory.slots[1]]
        
        # Create 3 unique (non-stackable) items
        self.world.item_templates["item_token"] = {"type": "Item", "name": "Token", "value": 1, "weight": 0.1}
        
        t1 = ItemFactory.create_item_from_template("item_token", self.world); t1.obj_id = "t1" # type: ignore
        t2 = ItemFactory.create_item_from_template("item_token", self.world); t2.obj_id = "t2" # type: ignore
        t3 = ItemFactory.create_item_from_template("item_token", self.world); t3.obj_id = "t3" # type: ignore
        
        # 1. Fill slots
        self.player.inventory.add_item(t1) # type: ignore
        self.player.inventory.add_item(t2) # type: ignore
        self.assertEqual(self.player.inventory.get_empty_slots(), 0)
        
        # 2. Attempt 3rd item
        success, msg = self.player.inventory.add_item(t3) # type: ignore
        
        self.assertFalse(success)
        self.assertIn("slots", msg.lower())
        self.assertEqual(self.player.inventory.count_item("t3"), 0)