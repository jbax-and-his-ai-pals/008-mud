# tests/singles/test_crafting_station.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingStation(GameTestBase):

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        
        # Define recipe requiring an Anvil
        self.world.item_templates["bar"] = {"type": "Item", "name": "Iron Bar", "value": 1}
        self.world.item_templates["sword"] = {"type": "Weapon", "name": "Sword", "value": 10}
        
        self.recipe = Recipe("test_forge", {
            "result_item_id": "sword",
            "station_required": "anvil",
            "ingredients": [{"item_id": "bar", "quantity": 1}]
        })
        self.manager.recipes["test_forge"] = self.recipe

    def test_crafting_without_station_fails(self):
        """Verify crafting fails if the required station is missing."""
        # Give ingredients
        bar = ItemFactory.create_item_from_template("bar", self.world)
        if bar: self.player.inventory.add_item(bar)
        
        # Act (No anvil in room)
        result = self.manager.craft(self.player, "test_forge")
        
        # Assert
        self.assertIn("need a Anvil", result)
        self.assertEqual(self.player.inventory.count_item("sword"), 0)

    def test_crafting_with_station_succeeds(self):
        """Verify crafting works when station is present."""
        # Give ingredients
        bar = ItemFactory.create_item_from_template("bar", self.world)
        if bar: self.player.inventory.add_item(bar)
        
        # Add Anvil to room
        self.world.item_templates["anvil_item"] = {
            "type": "Item", "name": "Blacksmith Anvil", 
            "properties": {"crafting_station_type": "anvil"}
        }
        anvil = ItemFactory.create_item_from_template("anvil_item", self.world)
        
        # FIX: Ensure IDs are strings (not None) before passing to add_item_to_room
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        
        if anvil and rid and room_id: 
            self.world.add_item_to_room(rid, room_id, anvil)
            
            # Act
            # Mock skill check to ensure success
            from unittest.mock import patch
            with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
                result = self.manager.craft(self.player, "test_forge")
            
            # Assert
            self.assertIn("Successfully crafted", result)
            self.assertEqual(self.player.inventory.count_item("sword"), 1)
        else:
            self.fail("Could not setup test: Player location or item invalid.")