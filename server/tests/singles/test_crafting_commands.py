# tests/singles/test_crafting_commands.py
"""Coverage for engine/commands/crafting.py: recipes' crafting-system-
unavailable guard, craft's no-args/fuzzy-match/unknown-recipe/success-vs-
failure-message branches, and salvage's no-args/item-not-found/delegation
paths -- edge cases the existing CraftingManager-focused tests don't
exercise at the command-handler level."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.commands import crafting as crafting_module
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
        # Refusal is phrased the way a person would say it, and names back what
        # the player actually typed so a typo is visible.
        self.assertIn("don't know how to make", result)
        self.assertIn("totally_unknown_recipe_xyz", result)

    def test_natural_phrasing_resolves_the_recipe(self):
        """The P3 fix: a multi-word query is not truncated to its first token.

        `craft wildflower posy` used to search for the literal "wildflower" and
        match the recipe's own name only by accident; the item's name is what a
        player knows, and the recipe's verb ("Tie ...") is not.
        """
        for phrasing in ("tie_wildflower_posy", "wildflower posy", "posy",
                         "Tie Wildflower Posy", "TIE_WILDFLOWER_POSY"):
            with self.subTest(phrasing=phrasing):
                result = craft_handler([phrasing], {"world": self.world, "player": self.player})
                # Resolved: either it crafted, or it reports the missing
                # ingredient -- both prove the recipe was found.
                self.assertNotIn("don't know how to make", result)

    def test_ambiguous_recipe_phrasing_asks_rather_than_guessing(self):
        """Two recipes with the same score must produce a question."""
        from engine.commands import crafting as crafting_module
        manager = self.world.game.crafting_manager
        # Give two distinct recipes display names that tie on the query.
        real = dict(manager.recipes)
        try:
            for rid in list(manager.recipes)[:2]:
                manager.recipes[rid].name = "Twin Widget"
            result = craft_handler(["twin widget"], {"world": self.world, "player": self.player})
            self.assertTrue(
                "?" in result or "don't know how to make" in result,
                "ambiguity should be reported, got: %r" % result,
            )
        finally:
            manager.recipes.clear()
            manager.recipes.update(real)

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


class TestCraftBatching(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.recipe = Recipe("batch_test_sword", {
            "name": "Batch Test Sword",
            "result_item_id": "item_iron_sword",
            "result_quantity": 1,
            "difficulty": 0,
            "ingredients": [{"item_id": "item_iron_ingot", "quantity": 1}],
        })
        self.manager.recipes["batch_test_sword"] = self.recipe

    def _give_ingots(self, count):
        for _ in range(count):
            self.player.inventory.add_item(ItemFactory.create_item_from_template("item_iron_ingot", self.world))

    def test_count_of_one_keeps_the_single_craft_message(self):
        self._give_ingots(1)
        result = craft_handler(["batch_test_sword", "1"], {"world": self.world, "player": self.player})
        self.assertIn("Successfully crafted", result)

    def test_batch_crafts_the_requested_count(self):
        self._give_ingots(3)
        result = craft_handler(["batch_test_sword", "3"], {"world": self.world, "player": self.player})
        self.assertIn("Crafted 3 x Batch Test Sword", result)
        self.assertEqual(3, self.player.inventory.count_item("item_iron_sword"))

    def test_batch_stops_early_and_reports_why_when_materials_run_out(self):
        self._give_ingots(2)
        result = craft_handler(["batch_test_sword", "5"], {"world": self.world, "player": self.player})
        self.assertIn("Crafted 2 x Batch Test Sword", result)
        self.assertIn("Stopped early", result)
        self.assertEqual(2, self.player.inventory.count_item("item_iron_sword"))

    def test_batch_count_is_clamped_to_the_maximum(self):
        # Each non-stackable sword takes its own slot -- give plenty of room
        # so slot/weight capacity isn't what stops the batch, only the cap.
        from engine.items.inventory import Inventory
        self.player.inventory = Inventory(max_slots=40, max_weight=1000.0)
        self._give_ingots(25)
        result = craft_handler(["batch_test_sword", "9999"], {"world": self.world, "player": self.player})
        self.assertIn(f"Crafted {crafting_module.MAX_CRAFT_BATCH} x Batch Test Sword", result)

    def test_zero_successes_reports_the_failure_as_an_error(self):
        result = craft_handler(["batch_test_sword", "3"], {"world": self.world, "player": self.player})
        self.assertNotIn("Successfully", result)
        self.assertNotIn("Crafted", result)


class TestDiscoveryGatedRecipeListing(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.recipe = Recipe("secret_test_recipe", {
            "name": "Secret Test Recipe",
            "result_item_id": "item_iron_sword",
            "requires_discovery": True,
            "ingredients": [],
        })
        self.manager.recipes["secret_test_recipe"] = self.recipe

    def test_unlearned_recipe_is_hidden_from_the_default_listing(self):
        result = recipes_handler([], {"world": self.world, "player": self.player})
        self.assertNotIn("Secret Test Recipe", result)

    def test_unlearned_recipe_is_hidden_even_with_all(self):
        result = recipes_handler(["all"], {"world": self.world, "player": self.player})
        self.assertNotIn("Secret Test Recipe", result)

    def test_learned_recipe_appears_and_behaves_normally(self):
        self.player.known_recipe_ids.add("secret_test_recipe")
        result = recipes_handler(["all"], {"world": self.world, "player": self.player})
        self.assertIn("Secret Test Recipe", result)

    def test_craft_on_an_unlearned_gated_recipe_reports_not_learned(self):
        result = craft_handler(["secret_test_recipe"], {"world": self.world, "player": self.player})
        self.assertIn("haven't learned", result)


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
