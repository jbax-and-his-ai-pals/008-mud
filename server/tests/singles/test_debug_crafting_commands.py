# tests/singles/test_debug_crafting_commands.py
"""Coverage for GM/debug crafting commands
(engine/commands/debug_crafting.py): givemats, spawnstation."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.crafting.recipe import Recipe


class TestGivematsCommand(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.manager.recipes["test_sword"] = Recipe("test_sword", {
            "name": "Test Sword",
            "result_item_id": "item_iron_sword",
            "result_quantity": 1,
            "station_required": "anvil",
            "ingredients": [{"item_id": "item_iron_ingot", "quantity": 2}],
        })

    def test_no_crafting_manager_is_reported(self):
        with patch.object(self.world.game, "crafting_manager", None):
            result = self.game.process_command("givemats test_sword")
        self.assertEqual("Crafting system not loaded.", result)

    def test_ingredient_creation_failure_is_skipped(self):
        with patch(
            "engine.commands.debug_crafting.ItemFactory.create_item_from_template", return_value=None,
        ):
            result = self.game.process_command("givemats test_sword")
        self.assertIn("(0 items)", result)

    def test_no_args_shows_usage(self):
        self.assertIn("Usage", self.game.process_command("givemats"))

    def test_unknown_recipe_is_reported(self):
        result = self.game.process_command("givemats not_a_real_recipe")
        self.assertIn("Recipe not found", result)

    def test_gives_ingredients_by_exact_id(self):
        result = self.game.process_command("givemats test_sword")
        self.assertIn("Added ingredients for Test Sword", result)
        self.assertEqual(2, self.player.inventory.count_item("item_iron_ingot"))

    def test_gives_ingredients_by_fuzzy_id(self):
        result = self.game.process_command("givemats sword")
        self.assertIn("Added ingredients", result)
        self.assertEqual(2, self.player.inventory.count_item("item_iron_ingot"))


class TestSpawnstationCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertIn("Usage", self.game.process_command("spawnstation"))

    def test_unknown_type_is_reported(self):
        result = self.game.process_command("spawnstation not_a_station")
        self.assertIn("Unknown station type", result)
        # The refusal names the station types this content set actually has,
        # because which items are stations is content-authored rather than a
        # fixed list in the engine.
        self.assertIn("anvil", result)
        self.assertIn("alchemy", result)

    def test_station_types_come_from_content(self):
        """Any item carrying a crafting_station_type is spawnable.

        `spawnable_stations` is authored in the ruleset; this asserts the
        engine resolves from that rather than from hardcoded item ids.
        """
        ruleset_stations = (self.world.ruleset_section("debug") or {}).get("spawnable_stations")
        self.assertIsInstance(ruleset_stations, dict)
        self.assertEqual(ruleset_stations.get("anvil"), "item_anvil")

        for label, item_id in ruleset_stations.items():
            with self.subTest(station=label):
                template = self.world.item_templates.get(item_id)
                self.assertIsNotNone(template, "%s names missing item %s" % (label, item_id))
                self.assertTrue(
                    template.get("properties", {}).get("crafting_station_type"),
                    "%s is not actually a crafting station" % item_id,
                )

    def test_spawns_anvil(self):
        result = self.game.process_command("spawnstation anvil")
        self.assertIn("Spawned", result)
        self.assertIsNotNone(self.world.find_item_in_room_for_player("Anvil", self.player) or
                              self.world.find_item_in_room_for_player("anvil", self.player))

    def test_spawns_alchemy_station(self):
        result = self.game.process_command("spawnstation alchemy")
        self.assertIn("Spawned", result)

    def test_without_player_location_reports_error(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("spawnstation anvil")
        self.assertEqual("Player location is unavailable.", result)

    def test_station_creation_failure_is_reported(self):
        with patch(
            "engine.commands.debug_crafting.ItemFactory.create_item_from_template", return_value=None,
        ):
            result = self.game.process_command("spawnstation anvil")
        self.assertEqual("Failed to create station.", result)
