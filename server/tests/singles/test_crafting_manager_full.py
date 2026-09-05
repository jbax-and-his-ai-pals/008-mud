# tests/singles/test_crafting_manager_full.py
"""Coverage for engine/crafting/crafting_manager.py: __init__'s content_root
mismatch guard, _load_recipes' missing-directory/non-json-skip/malformed-
file branches, get_nearby_stations' no-player guard and no-station-
property skip, craft()'s unknown-recipe/missing-result-item/failed-item-
creation branches, and salvage()'s leather/default-fallback categories
and unknown-output-template guard."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.crafting.crafting_manager import CraftingManager
from engine.crafting.recipe import Recipe
from engine.items.item import Item
from engine.items.item_factory import ItemFactory


class TestInit(GameTestBase):
    def test_mismatched_content_root_raises(self):
        with self.assertRaises(TypeError):
            CraftingManager(self.world, content_root="/some/other/path")


class TestLoadRecipes(GameTestBase):
    def setUp(self):
        super().setUp()
        self.tmp_root = tempfile.mkdtemp()
        self.original_content_root = self.world.content_root
        self.world.content_root = self.tmp_root

    def tearDown(self):
        self.world.content_root = self.original_content_root
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().tearDown()

    def test_missing_directory_results_in_no_recipes(self):
        manager = CraftingManager(self.world)
        self.assertEqual(manager.recipes, {})

    def test_non_json_files_are_skipped(self):
        crafting_dir = os.path.join(self.tmp_root, "crafting")
        os.makedirs(crafting_dir)
        with open(os.path.join(crafting_dir, "readme.txt"), "w") as f:
            f.write("not json")
        manager = CraftingManager(self.world)
        self.assertEqual(manager.recipes, {})

    def test_malformed_json_file_is_logged_and_skipped(self):
        crafting_dir = os.path.join(self.tmp_root, "crafting")
        os.makedirs(crafting_dir)
        with open(os.path.join(crafting_dir, "broken.json"), "w") as f:
            f.write("{not valid json")
        manager = CraftingManager(self.world)
        self.assertEqual(manager.recipes, {})


class TestGetNearbyStations(GameTestBase):
    def test_no_resolvable_player_returns_empty_list(self):
        manager = self.game.crafting_manager
        with patch.object(self.world, "resolve_reference_player", return_value=None):
            result = manager.get_nearby_stations(player=None)
        self.assertEqual(result, [])

    def test_items_without_station_property_are_skipped(self):
        manager = self.game.crafting_manager
        plain_item = Item(name="Plain Rock")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, plain_item)
        result = manager.get_nearby_stations(self.player)
        self.assertEqual(result, [])


class TestCraft(GameTestBase):
    def test_unknown_recipe_returns_message(self):
        manager = self.game.crafting_manager
        result = manager.craft(self.player, "totally_bogus_recipe_xyz")
        self.assertEqual(result, "Unknown recipe.")

    def test_missing_result_item_id_returns_message(self):
        manager = self.game.crafting_manager
        manager.recipes["broken_recipe"] = Recipe("broken_recipe", {"name": "Broken"})
        result = manager.craft(self.player, "broken_recipe")
        self.assertIn("Missing result item", result)

    def test_failed_result_item_creation_aborts_crafting(self):
        manager = self.game.crafting_manager
        manager.recipes["test_recipe_fail_create"] = Recipe(
            "test_recipe_fail_create",
            {"name": "Test Recipe", "result_item_id": "item_iron_sword", "ingredients": []},
        )
        with patch("engine.crafting.crafting_manager.SkillSystem.attempt_check", return_value=(True, "Success!")):
            with patch("engine.crafting.crafting_manager.ItemFactory.create_item_from_template", return_value=None):
                result = manager.craft(self.player, "test_recipe_fail_create")
        self.assertIn("Crafting aborted", result)


class TestSalvage(GameTestBase):
    def test_leather_item_salvages_to_leather_scraps(self):
        manager = self.game.crafting_manager
        item = Item(name="Leather Boots", weight=2.0)
        self.player.inventory.add_item(item)
        stand_in_material = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        with patch(
            "engine.crafting.crafting_manager.ItemFactory.create_item_from_template",
            return_value=stand_in_material,
        ) as mock_create:
            manager.salvage(self.player, item)
        mock_create.assert_called_once_with("item_leather_scraps", self.world)

    def test_unrecognized_item_uses_default_scrap_fallback(self):
        manager = self.game.crafting_manager
        item = Item(name="Mystery Trinket", weight=1.0)
        self.player.inventory.add_item(item)
        stand_in_material = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        with patch(
            "engine.crafting.crafting_manager.ItemFactory.create_item_from_template",
            return_value=stand_in_material,
        ) as mock_create:
            manager.salvage(self.player, item)
        mock_create.assert_called_once_with("item_scrap", self.world)

    def test_unknown_output_template_reports_cannot_salvage(self):
        manager = self.game.crafting_manager
        item = Item(name="Mystery Trinket", weight=1.0)
        self.player.inventory.add_item(item)
        with patch("engine.crafting.crafting_manager.ItemFactory.create_item_from_template", return_value=None):
            result = manager.salvage(self.player, item)
        self.assertIn("cannot salvage", result)


if __name__ == "__main__":
    unittest.main()
