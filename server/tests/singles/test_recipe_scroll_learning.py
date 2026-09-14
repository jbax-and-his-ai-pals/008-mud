# tests/singles/test_recipe_scroll_learning.py
"""Coverage for Player.learn_recipe and Consumable's "learn_recipe" effect
type -- the recipe-discovery counterpart of test_scroll_learning.py's
"learn_spell" coverage."""

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.crafting.recipe import Recipe


class TestRecipeScrollLearning(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.manager.recipes["scroll_test_recipe"] = Recipe("scroll_test_recipe", {
            "name": "Scroll Test Recipe",
            "result_item_id": "item_iron_sword",
            "requires_discovery": True,
            "ingredients": [],
        })
        self.world.item_templates["scroll_test_pattern"] = {
            "type": "Consumable", "name": "Pattern of Test", "value": 10,
            "properties": {
                "effect_type": "learn_recipe",
                "recipe_to_learn": "scroll_test_recipe",
                "uses": 1,
            },
        }

    def test_learn_unknown_recipe(self):
        """Using a scroll teaches the recipe and consumes the item."""
        scroll = ItemFactory.create_item_from_template("scroll_test_pattern", self.world)
        self.player.inventory.add_item(scroll)

        result = scroll.use(self.player)

        self.assertIn("successfully learn", result)
        self.assertIn("scroll_test_recipe", self.player.known_recipe_ids)
        self.assertEqual(scroll.get_property("uses"), 0)

    def test_learn_known_recipe_prevention(self):
        """Using a scroll for an already-known recipe doesn't consume it."""
        self.player.known_recipe_ids.add("scroll_test_recipe")

        scroll = ItemFactory.create_item_from_template("scroll_test_pattern", self.world)
        self.player.inventory.add_item(scroll)

        result = scroll.use(self.player)

        self.assertIn("already know", result.lower())
        self.assertEqual(scroll.get_property("uses"), 1)

    def test_learn_recipe_referencing_an_unknown_id_reports_failure(self):
        self.world.item_templates["scroll_bad_pattern"] = {
            "type": "Consumable", "name": "Pattern of Nothing", "value": 10,
            "properties": {
                "effect_type": "learn_recipe",
                "recipe_to_learn": "totally_bogus_recipe_xyz",
                "uses": 1,
            },
        }
        scroll = ItemFactory.create_item_from_template("scroll_bad_pattern", self.world)
        self.player.inventory.add_item(scroll)

        result = scroll.use(self.player)

        self.assertIn("non-existent", result)
        self.assertEqual(scroll.get_property("uses"), 1)

    def test_misconfigured_scroll_with_no_recipe_property_is_inert(self):
        self.world.item_templates["scroll_empty_pattern"] = {
            "type": "Consumable", "name": "Blank Pattern", "value": 10,
            "properties": {"effect_type": "learn_recipe", "uses": 1},
        }
        scroll = ItemFactory.create_item_from_template("scroll_empty_pattern", self.world)
        self.player.inventory.add_item(scroll)

        result = scroll.use(self.player)

        self.assertIn("inert or misconfigured", result)


class TestPlayerLearnRecipe(GameTestBase):
    def setUp(self):
        super().setUp()
        self.game.crafting_manager.recipes["direct_test_recipe"] = Recipe("direct_test_recipe", {
            "name": "Direct Test Recipe", "result_item_id": "item_iron_sword", "ingredients": [],
        })

    def test_learning_an_unknown_recipe_id_fails(self):
        learned, message = self.player.learn_recipe("totally_bogus_recipe_xyz")
        self.assertFalse(learned)
        self.assertIn("non-existent", message)

    def test_learning_a_real_recipe_succeeds(self):
        learned, message = self.player.learn_recipe("direct_test_recipe")
        self.assertTrue(learned)
        self.assertIn("Direct Test Recipe", message)
        self.assertIn("direct_test_recipe", self.player.known_recipe_ids)

    def test_learning_an_already_known_recipe_fails(self):
        self.player.known_recipe_ids.add("direct_test_recipe")
        learned, message = self.player.learn_recipe("direct_test_recipe")
        self.assertFalse(learned)
        self.assertIn("already know", message)


if __name__ == "__main__":
    import unittest
    unittest.main()
