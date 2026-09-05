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
        self.assertEqual("Unknown station type.", result)

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
