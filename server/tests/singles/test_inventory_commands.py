# tests/singles/test_inventory_commands.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestInventoryCommands(GameTestBase):

    def setUp(self):
        super().setUp()
        # Inject templates
        self.world.item_templates["item_iron_sword"] = {
            "type": "Weapon", "name": "iron sword", "value": 50, "weight": 3.0,
            "properties": { "damage": 8, "equip_slot": ["main_hand"] }
        }
        self.world.item_templates["item_empty_crate"] = {
            "type": "Container", "name": "crate", "value": 1, "weight": 5.0,
            "properties": { "capacity": 10.0, "is_open": True }
        }

    def test_get_command(self):
        """Verify picking up an item."""
        # 1. Create Sword in Room
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if not sword:
            self.fail("Failed to create sword item.")
            return

        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        
        # Pylance guard
        if rid and room_id:
             self.world.add_item_to_room(rid, room_id, sword)
        else:
             self.fail("Player location is invalid.")

        # 2. Act
        result = self.game.process_command("get iron sword")
        
        # 3. Assert
        self.assertIsNotNone(result)
        if result:
             self.assertIn("You pick up", result)
             
        # Check Inventory
        self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 1)
        
        # Check Room (Should be empty of that item)
        room_items = self.world.get_items_in_current_room()
        self.assertFalse(any(i.obj_id == "item_iron_sword" for i in room_items))

    def test_drop_command(self):
        """Verify dropping an item."""
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            self.player.inventory.add_item(sword)
            
            # Act
            result = self.game.process_command("drop iron sword")
            
            # Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("You drop", result)
                
            self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 0)
            
            # Check Room
            room_items = self.world.get_items_in_current_room()
            self.assertTrue(any(i.obj_id == "item_iron_sword" for i in room_items))

    def test_put_in_container(self):
        """Verify putting item inside a container."""
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        crate = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        
        if sword and isinstance(crate, Container):
            self.player.inventory.add_item(sword)
            
            # Place crate in room
            rid = self.player.current_region_id
            room_id = self.player.current_room_id
            if rid and room_id:
                self.world.add_item_to_room(rid, room_id, crate)
                
                # Act
                result = self.game.process_command("put iron sword in crate")
                
                # Assert
                self.assertIsNotNone(result)
                if result:
                    self.assertIn("You put", result)
                    
                self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 0)
                self.assertEqual(len(crate.properties["contains"]), 1)
            else:
                 self.fail("Player location invalid.")

    def test_get_from_container(self):
        """Verify taking item from a container."""
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        crate_item = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        
        if sword and isinstance(crate_item, Container):
            crate = cast(Container, crate_item)
            crate.add_item(sword)
            
            rid = self.player.current_region_id
            room_id = self.player.current_room_id
            if rid and room_id:
                 self.world.add_item_to_room(rid, room_id, crate)
                 
                 # Act
                 result = self.game.process_command("get iron sword from crate")
                 
                 # Assert
                 self.assertIsNotNone(result)
                 if result:
                      self.assertIn("You get", result)
                      
                 self.assertEqual(self.player.inventory.count_item("item_iron_sword"), 1)
                 self.assertEqual(len(crate.properties["contains"]), 0)
            else:
                 self.fail("Player location invalid.")
