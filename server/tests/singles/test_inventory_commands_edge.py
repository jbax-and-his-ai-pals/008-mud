# tests/singles/test_inventory_commands_edge.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestInventoryCommandsEdge(GameTestBase):
    
    def test_get_all_empty_room(self):
        """Verify 'get all' feedback when room is empty."""
        room = self.world.get_current_room()
        if room:
            room.items = []
            
        result = self.game.process_command("get all")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("nothing here", result.lower())

    def test_open_non_container(self):
        """Verify feedback when trying to open a non-container."""
        # Inject template to ensure sword exists
        self.world.item_templates["item_iron_sword"] = {
            "type": "Weapon", "name": "iron sword", "value": 50, "weight": 3.0,
            "properties": { "damage": 8, "equip_slot": ["main_hand"] }
        }
        
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            self.world.add_item_to_room(self.player.current_region_id or "", self.player.current_room_id or "", sword)
            
        result = self.game.process_command(f"open iron sword")
        self.assertIsNotNone(result)
        if result:
            # This should now pass with the updated open_handler
            self.assertIn("not a container", result.lower())

    def test_take_all_from_closed_container(self):
        """Verify items inside closed containers are not taken by 'get all'."""
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "value": 1, 
            "properties": { "is_open": False, "capacity": 10 }
        }
        item_box = ItemFactory.create_item_from_template("box", self.world)
        ruby = ItemFactory.create_item_from_template("item_ruby", self.world)
        
        # Verify types for Pylance
        if isinstance(item_box, Container) and ruby:
            box = cast(Container, item_box)
            box.add_item(ruby)
            
            self.world.add_item_to_room(self.player.current_region_id or "", self.player.current_room_id or "", box)
            
            # 'get all' should take the box, but not the ruby inside it
            self.game.process_command("get all")
            
            self.assertEqual(self.player.inventory.count_item("box"), 1)
            self.assertEqual(self.player.inventory.count_item("item_ruby"), 0)