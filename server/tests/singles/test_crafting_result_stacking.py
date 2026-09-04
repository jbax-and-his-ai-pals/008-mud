# tests/singles/test_crafting_result_stacking.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingResultStacking(GameTestBase):

    def test_crafting_stacks_output(self):
        """Verify crafted items stack with existing inventory items."""
        # Recipe: 1 Log -> 1 Arrow (Stackable)
        self.world.item_templates["log"] = {"type": "Item", "name": "Log", "value": 1}
        self.world.item_templates["arrow"] = {"type": "Item", "name": "Arrow", "value": 1, "stackable": True}
        
        recipe = Recipe("make_arrow", {
            "result_item_id": "arrow", "ingredients": [{"item_id": "log", "quantity": 1}]
        })
        self.game.crafting_manager.recipes["make_arrow"] = recipe
        
        # 1. Have 1 Arrow already
        arrow = ItemFactory.create_item_from_template("arrow", self.world)
        if arrow: self.player.inventory.add_item(arrow, 1)
        
        # 2. Have Ingredient
        log = ItemFactory.create_item_from_template("log", self.world)
        if log: self.player.inventory.add_item(log, 1)
        
        # 3. Craft
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
            self.game.crafting_manager.craft(self.player, "make_arrow")
            
        # 4. Assert: 1 Stack of 2 Arrows
        self.assertEqual(self.player.inventory.count_item("arrow"), 2)
        # Check slot usage
        slots_used = len([s for s in self.player.inventory.slots if s.item])
        self.assertEqual(slots_used, 1)