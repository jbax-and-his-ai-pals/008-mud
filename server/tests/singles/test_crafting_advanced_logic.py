# tests/singles/test_crafting_advanced_logic.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingAdvancedLogic(GameTestBase):

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        
        # Define complex recipe: 2 Wood + 1 Iron -> 10 Arrows
        self.world.item_templates["item_wood"] = {"type": "Item", "name": "wood", "value": 1}
        self.world.item_templates["item_iron"] = {"type": "Item", "name": "iron", "value": 1}
        self.world.item_templates["item_arrow"] = {"type": "Item", "name": "arrow", "value": 1, "stackable": True}
        
        self.recipe = Recipe("bundle_arrows", {
            "name": "Bundle of Arrows",
            "result_item_id": "item_arrow",
            "result_quantity": 10,
            "ingredients": [
                {"item_id": "item_wood", "quantity": 2},
                {"item_id": "item_iron", "quantity": 1}
            ]
        })
        self.manager.recipes["bundle_arrows"] = self.recipe

    def test_multi_ingredient_consumption(self):
        """Verify multiple types of materials are consumed correctly."""
        # 1. Provide materials
        wood = ItemFactory.create_item_from_template("item_wood", self.world)
        iron = ItemFactory.create_item_from_template("item_iron", self.world)
        if wood and iron and self.player:
            self.player.inventory.add_item(wood, 2)
            self.player.inventory.add_item(iron, 1)
            
            # 2. Craft
            with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "Success")):
                self.manager.craft(self.player, "bundle_arrows")
                
            # 3. Assertions
            self.assertEqual(self.player.inventory.count_item("item_wood"), 0)
            self.assertEqual(self.player.inventory.count_item("item_iron"), 0)
            self.assertEqual(self.player.inventory.count_item("item_arrow"), 10)