# tests/singles/test_recipe_model.py
"""Coverage for engine/crafting/recipe.py's station_display property with
an actual station_required value set."""

import unittest

from engine.crafting.recipe import Recipe


class TestRecipeStationDisplay(unittest.TestCase):
    def test_station_required_is_formatted_for_display(self):
        recipe = Recipe("test_recipe", {"name": "Test", "station_required": "alchemy_table"})
        self.assertEqual(recipe.station_display, "Alchemy Table")

    def test_no_station_required_is_handcrafting(self):
        recipe = Recipe("test_recipe", {"name": "Test"})
        self.assertEqual(recipe.station_display, "Handcrafting")


if __name__ == "__main__":
    unittest.main()
