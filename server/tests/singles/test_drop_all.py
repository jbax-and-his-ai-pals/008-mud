# tests/singles/test_drop_all.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestDropAll(GameTestBase):

    def test_drop_all_functionality(self):
        """Verify 'drop all' clears inventory and populates room."""
        # 1. Add diverse items
        self.world.item_templates["stone"] = {"type": "Item", "name": "Stone", "value": 0}
        
        for _ in range(5):
            item = ItemFactory.create_item_from_template("stone", self.world)
            if item: self.player.inventory.add_item(item)
            
        self.assertEqual(self.player.inventory.count_item("stone"), 5)
        
        # 2. Act
        result = self.game.process_command("drop all")
        
        # 3. Assert Inventory Empty
        self.assertEqual(self.player.inventory.count_item("stone"), 0)
        self.assertEqual(self.player.inventory.get_empty_slots(), self.player.inventory.max_slots)
        
        # 4. Assert Room Populated
        room_items = self.world.get_items_in_current_room()
        # Items might stack in room logic depending on implementation, 
        # or exist as separate entities. The base add_item_to_room appends to list.
        # Check if 5 items were dropped.
        stones_in_room = [i for i in room_items if i.name == "Stone"]
        self.assertEqual(len(stones_in_room), 5)