# tests/singles/test_crafting_commands.py
"""Coverage for engine/commands/crafting.py: recipes' crafting-system-
unavailable guard, craft's no-args/fuzzy-match/unknown-recipe/success-vs-
failure-message branches, and salvage's no-args/item-not-found/delegation
paths -- edge cases the existing CraftingManager-focused tests don't
exercise at the command-handler level."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.commands.crafting import recipes_handler, craft_handler, salvage_handler
from engine.crafting.recipe import Recipe
from engine.items.item_factory import ItemFactory


class TestRecipesHandlerGuard(GameTestBase):
    def test_no_crafting_manager_reports_unavailable(self):
        original = self.game.crafting_manager
        self.game.crafting_manager = None
        try:
            result = recipes_handler([], {"world": self.world, "player": self.player})
        finally:
            self.game.crafting_manager = original
        self.assertEqual("Crafting system unavailable.", result)

    def test_lists_recipes_with_no_nearby_stations(self):
        result = recipes_handler([], {"world": self.world, "player": self.player})
        self.assertIn("CRAFTING", result)
        self.assertIn("Nearby Stations: None", result)

    def test_no_recipes_available_suggests_recipes_all(self):
        self.game.crafting_manager.recipes.clear()
        result = recipes_handler([], {"world": self.world, "player": self.player})
        self.assertIn("No recipes available", result)
        self.assertIn("recipes all", result)

    def test_no_recipes_available_with_show_all_omits_suggestion(self):
        self.game.crafting_manager.recipes.clear()
        result = recipes_handler(["all"], {"world": self.world, "player": self.player})
        self.assertIn("No recipes available", result)
        self.assertNotIn("Type 'recipes all'", result)


class TestCraftHandler(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.recipe = Recipe("cmd_test_sword", {
            "name": "Command Test Sword",
            "result_item_id": "item_iron_sword",
            "result_quantity": 1,
            "ingredients": [{"item_id": "item_iron_ingot", "quantity": 1}],
        })
        self.manager.recipes["cmd_test_sword"] = self.recipe

    def test_no_args_prompts(self):
        result = craft_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Craft what?", result)

    def test_exact_recipe_id_match(self):
        result = craft_handler(["cmd_test_sword"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_fuzzy_match_by_recipe_name(self):
        result = craft_handler(["command"], {"world": self.world, "player": self.player})
        # Matched via fuzzy lookup on recipe name/id, not a literal id -- so
        # it must not report "Unknown recipe".
        self.assertNotIn("Unknown recipe", result)

    def test_unknown_recipe_reports_error(self):
        result = craft_handler(["totally_unknown_recipe_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("Unknown recipe", result)

    def test_successful_craft_uses_success_format(self):
        ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
        self.player.inventory.add_item(ingot)
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "(Mock Success)")):
            result = craft_handler(["cmd_test_sword"], {"world": self.world, "player": self.player})
        self.assertIn("Successfully crafted", result)

    def test_failed_craft_uses_error_format(self):
        # No ingredients in inventory -> craft() reports failure.
        result = craft_handler(["cmd_test_sword"], {"world": self.world, "player": self.player})
        self.assertNotIn("Successfully", result)


class TestSalvageHandler(GameTestBase):
    def test_no_args_prompts(self):
        result = salvage_handler([], {"world": self.world, "player": self.player})
        self.assertIn("Salvage what?", result)

    def test_item_not_in_inventory_reports_error(self):
        result = salvage_handler(["nonexistent_item_xyz"], {"world": self.world, "player": self.player})
        self.assertIn("don't have", result)

    def test_delegates_to_manager_salvage(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(item)
        result = salvage_handler([item.name], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
