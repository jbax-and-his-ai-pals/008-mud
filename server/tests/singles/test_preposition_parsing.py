# tests/singles/test_preposition_parsing.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestPrepositionParsing(GameTestBase):

    def setUp(self):
        super().setUp()
        # Ensure template exists
        self.world.item_templates["bag"] = {
            "type": "Container", "name": "leather bag", "value": 1, "weight": 1.0,
            "properties": { "is_open": True, "capacity": 10 }
        }

    def test_get_from_specific_container(self):
        """Verify player can target a specific container in the room."""
        # 1. Setup Room: A Bag containing a Ruby
        item_bag = ItemFactory.create_item_from_template("bag", self.world)
        ruby_template = self.world.item_templates.get("item_ruby")
        
        if isinstance(item_bag, Container) and ruby_template and self.player:
            bag = cast(Container, item_bag)
            ruby = ItemFactory.create_item_from_template("item_ruby", self.world)
            
            if ruby:
                bag.add_item(ruby)
                
            rid = self.player.current_region_id
            room_id = self.player.current_room_id
            
            if rid and room_id:
                self.world.add_item_to_room(rid, room_id, bag)
            
                # 2. Setup Distraction: Another Ruby on the floor
                ruby_floor = ItemFactory.create_item_from_template("item_ruby", self.world)
                if ruby_floor:
                    self.world.add_item_to_room(rid, room_id, ruby_floor)
                    
                # 3. Act: Get ONLY the ruby from the bag
                result = self.game.process_command("get ruby from leather bag")
                
                # 4. Assert
                self.assertIsNotNone(result, "Command result should not be None")
                if result:
                    self.assertIn("from the leather bag", result.lower())
                
                self.assertEqual(self.player.inventory.count_item("item_ruby"), 1)
                self.assertEqual(len(bag.properties.get("contains", [])), 0)
                
                # The ruby on the floor should still be in the room
                found_on_floor = self.world.find_item_in_room("ruby")
                self.assertIsNotNone(found_on_floor, "The ruby on the floor should still exist.")

    def test_put_preposition(self):
        """Verify 'put X in Y' syntax handles container targeting correctly."""
        item_bag = ItemFactory.create_item_from_template("bag", self.world)
        ruby = ItemFactory.create_item_from_template("item_ruby", self.world)
        
        if isinstance(item_bag, Container) and ruby and self.player:
            bag = cast(Container, item_bag)
            self.player.inventory.add_item(ruby)
            
            rid = self.player.current_region_id
            room_id = self.player.current_room_id
            
            if rid and room_id:
                self.world.add_item_to_room(rid, room_id, bag)
            
                result = self.game.process_command("put ruby in leather bag")
                
                self.assertIsNotNone(result, "Command result should not be None")
                if result:
                    self.assertIn("you put", result.lower())
                    
                self.assertEqual(len(bag.properties.get("contains", [])), 1)
                self.assertEqual(self.player.inventory.count_item("item_ruby"), 0)