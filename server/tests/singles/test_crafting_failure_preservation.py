# tests/singles/test_crafting_failure_preservation.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe

class TestCraftingFailurePreservation(GameTestBase):

    def setUp(self):
        super().setUp()
        # Setup Recipe
        self.world.item_templates["test_ingot"] = {"type": "Item", "name": "Ingot", "value": 1}
        self.world.item_templates["test_sword"] = {"type": "Weapon", "name": "Sword", "value": 100}
        
        self.recipe = Recipe("fail_test", {
            "result_item_id": "test_sword",
            "ingredients": [{"item_id": "test_ingot", "quantity": 1}]
        })
        self.game.crafting_manager.recipes["fail_test"] = self.recipe

    def test_mats_kept_on_failure(self):
        """Verify materials remain in inventory after a failed craft attempt."""
        # 1. Give Player Mats
        ingot = ItemFactory.create_item_from_template("test_ingot", self.world)
        if ingot and self.player:
            self.player.inventory.add_item(ingot)
            self.assertEqual(self.player.inventory.count_item("test_ingot"), 1)
            
            # 2. Force Failure
            with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(False, "(Mock Failure)")):
                result = self.game.crafting_manager.craft(self.player, "fail_test")
                self.assertIn("failed", result.lower())

            # 3. Assert Mats are still there
            self.assertEqual(self.player.inventory.count_item("test_ingot"), 1, "Ingredients should not be consumed on failure.")
            self.assertEqual(self.player.inventory.count_item("test_sword"), 0)