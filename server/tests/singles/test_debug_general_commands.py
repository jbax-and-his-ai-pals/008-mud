# tests/singles/test_debug_general_commands.py
"""Coverage for GM/debug general commands (engine/commands/debug/general.py):
refresh, ignoreplayer, debug_commands, testrefactor."""

from unittest.mock import patch

from tests.fixtures import GameTestBase


class TestRefreshCommand(GameTestBase):
    def test_no_player_reports_not_found(self):
        from engine.commands.debug.general import refresh_handler
        result = refresh_handler([], {"player": None})
        self.assertEqual("Player not found.", result)

    def test_restores_health_mana_and_cooldowns(self):
        self.player.health = 1
        self.player.runtime_state.magic.mana = 0
        self.player.runtime_state.magic.cooldowns = {"minor_heal": 999.0}
        self.player.last_attack_time = 999.0

        result = self.game.process_command("refresh")

        self.assertIn("restored", result)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(self.player.runtime_state.magic.max_mana, self.player.runtime_state.magic.mana)
        self.assertEqual({}, self.player.runtime_state.magic.cooldowns)
        self.assertEqual(0, self.player.last_attack_time)


class TestIgnorePlayerCommand(GameTestBase):
    def test_no_args_reports_current_status(self):
        result = self.game.process_command("ignoreplayer")
        self.assertIn("Usage", result)
        self.assertIn("Currently:", result)

    def test_invalid_arg_reports_current_status(self):
        result = self.game.process_command("ignoreplayer maybe")
        self.assertIn("Usage", result)

    def test_on_sets_ignore_flag(self):
        result = self.game.process_command("ignoreplayer on")
        self.assertIn("ignore you", result)
        self.assertTrue(self.game.debug_ignore_player)

    def test_off_clears_ignore_flag(self):
        self.game.process_command("ignoreplayer on")
        result = self.game.process_command("ignoreplayer off")
        self.assertIn("engage you normally", result)
        self.assertFalse(self.game.debug_ignore_player)


class TestDebugCommandsCommand(GameTestBase):
    def test_reports_registry_state(self):
        result = self.game.process_command("debug_commands")
        self.assertIn("Command Registry State", result)
        self.assertIn("Total Registered Names/Aliases", result)
        self.assertIn("Commands by Category", result)

    def test_empty_registry_is_reported(self):
        with patch("engine.commands.debug.general.registered_commands", {}):
            result = self.game.process_command("debug_commands")
        self.assertIn("No commands are registered!", result)


class TestTestRefactorCommand(GameTestBase):
    def test_no_player_reports_not_found(self):
        from engine.commands.debug.general import test_refactor_handler
        result = test_refactor_handler([], {"world": self.world, "player": None})
        self.assertEqual("Player not found.", result)

    def test_sets_up_the_lock_unlock_scenario(self):
        result = self.game.process_command("testrefactor")
        self.assertIn("LOCK/UNLOCK TEST INITIALIZED", result)

        chest = self.world.find_item_in_room_for_player("Refactor Chest", self.player)
        self.assertIsNotNone(chest)
        self.assertTrue(chest.properties.get("locked"))
        self.assertIsNotNone(self.player.inventory.find_item_by_name("Refactor Key"))
        self.assertIsNotNone(self.player.inventory.find_item_by_name("debug lockpick"))

    def test_running_twice_replaces_the_existing_chest(self):
        self.game.process_command("testrefactor")
        self.game.process_command("testrefactor")
        matches = [
            item for item in self.world.get_items_in_current_room()
            if item.name == "Refactor Chest"
        ]
        self.assertEqual(1, len(matches))

    def test_without_player_location_reports_error(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("testrefactor")
        self.assertEqual("Player location unavailable.", result)
