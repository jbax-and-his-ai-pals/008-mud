# tests/singles/test_crafting_manager_full.py
"""Coverage for engine/crafting/crafting_manager.py: __init__'s content_root
mismatch guard, _load_recipes' missing-directory/non-json-skip/malformed-
file branches, get_nearby_stations' no-player guard and no-station-
property skip, craft()'s unknown-recipe/missing-result-item/failed-item-
creation branches, and salvage()'s per-item salvage_output override,
ruleset class-keyed rule, default-fallback, and unknown-output-template
guard."""

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
from engine.items.weapon import Weapon


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

    def test_authoring_note_keys_are_not_read_as_recipes(self):
        """`_comment` is an authoring note, and every other loader skips it.

        This one crashed on it -- `'str' object has no attribute 'get'` -- and,
        because one bad key aborts the whole file, a single note at the top of
        an orbital-salvage recipe file silently removed every recipe in it.
        """
        crafting_dir = os.path.join(self.tmp_root, "crafting")
        os.makedirs(crafting_dir)
        with open(os.path.join(crafting_dir, "notes.json"), "w") as f:
            json.dump({
                "_comment": "A note to the reader, not a recipe.",
                "make_thing": {"name": "Make Thing", "result_item_id": "item_x"},
            }, f)
        manager = CraftingManager(self.world)
        self.assertEqual(["make_thing"], list(manager.recipes))

    def test_a_recipe_that_is_not_an_object_is_skipped_not_crashed(self):
        crafting_dir = os.path.join(self.tmp_root, "crafting")
        os.makedirs(crafting_dir)
        with open(os.path.join(crafting_dir, "mixed.json"), "w") as f:
            json.dump({
                "make_thing": {"name": "Make Thing", "result_item_id": "item_x"},
                "typo": "this should have been an object",
            }, f)
        manager = CraftingManager(self.world)
        self.assertEqual(["make_thing"], list(manager.recipes))


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


class TestDiscoveryGate(GameTestBase):
    """A recipe authored with requires_discovery stays unusable until the
    player has it in known_recipe_ids -- every recipe without that flag
    (i.e. every recipe that existed before this feature) is unaffected."""

    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.recipe = Recipe("gated_test_recipe", {
            "name": "Gated Test Recipe",
            "result_item_id": "item_iron_sword",
            "requires_discovery": True,
            "ingredients": [],
        })
        self.manager.recipes["gated_test_recipe"] = self.recipe

    def test_unlearned_recipe_cannot_be_crafted(self):
        can_do, message = self.manager.can_craft(self.player, self.recipe)
        self.assertFalse(can_do)
        self.assertIn("haven't learned", message)

    def test_learned_recipe_passes_the_discovery_check(self):
        self.player.known_recipe_ids.add("gated_test_recipe")
        can_do, _ = self.manager.can_craft(self.player, self.recipe)
        self.assertTrue(can_do)

    def test_recipes_without_the_flag_are_unaffected(self):
        ordinary = Recipe("ordinary_test_recipe", {
            "name": "Ordinary", "result_item_id": "item_iron_sword", "ingredients": [],
        })
        can_do, _ = self.manager.can_craft(self.player, ordinary)
        self.assertTrue(can_do)


class TestSalvage(GameTestBase):
    def test_item_level_salvage_output_override_is_honored(self):
        manager = self.game.crafting_manager
        item = Item(name="Leather Boots", weight=2.0)
        item.update_property("salvage_output", {"item_id": "item_leather_scraps", "quantity_per_weight": 1.0})
        self.player.inventory.add_item(item)
        stand_in_material = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        with patch(
            "engine.crafting.crafting_manager.ItemFactory.create_item_from_template",
            return_value=stand_in_material,
        ) as mock_create:
            manager.salvage(self.player, item)
        mock_create.assert_called_once_with("item_leather_scraps", self.world)

    def test_fantasy_leather_cap_salvages_to_existing_crafting_material(self):
        manager = self.game.crafting_manager
        cap = ItemFactory.create_item_from_template("item_leather_cap", self.world)
        self.assertIsNotNone(cap)
        self.player.inventory.add_item(cap)

        result = manager.salvage(self.player, cap)

        self.assertIn("recover", result)
        self.assertEqual(0, self.player.inventory.count_item("item_leather_cap"))
        self.assertEqual(1, self.player.inventory.count_item("item_leather_strip"))

    def test_a_family_keyed_ruleset_rule_is_used(self):
        """fantasy_frontier keys salvage on the item's family, not its class.

        The class key was a proxy for the family, so this is the same rule said
        more precisely -- and it reaches a weapon template the ruleset never
        named, which is what the family is for.
        """
        manager = self.game.crafting_manager
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        self.assertEqual("weapon", sword.get_property("item_family"))
        self.player.inventory.add_item(sword)
        stand_in_material = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        with patch(
            "engine.crafting.crafting_manager.ItemFactory.create_item_from_template",
            return_value=stand_in_material,
        ) as mock_create:
            manager.salvage(self.player, sword)
        # fantasy_frontier's ruleset maps the `weapon` family -> item_iron_ingot
        # at 0.5/weight.
        mock_create.assert_called_once_with("item_iron_ingot", self.world)

    def test_a_bare_instance_with_no_family_falls_through_to_the_default(self):
        """A `Weapon` that belongs to nothing has no rule to be found under.

        Naming an engine class was how content used to describe a kind of thing;
        now that a kind of thing is a family, an instance from outside the
        content set lands on the set's scrap rather than on a rule that was
        never really about it.
        """
        manager = self.game.crafting_manager
        weapon = Weapon(name="Test Blade", weight=4.0)
        self.player.inventory.add_item(weapon)
        stand_in_material = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        with patch(
            "engine.crafting.crafting_manager.ItemFactory.create_item_from_template",
            return_value=stand_in_material,
        ) as mock_create:
            manager.salvage(self.player, weapon)
        mock_create.assert_called_once_with("item_scrap", self.world)

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
