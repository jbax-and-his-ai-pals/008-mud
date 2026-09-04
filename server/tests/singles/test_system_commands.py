# tests/singles/test_system_commands.py
"""Coverage for engine/commands/system.py: help, stop, quit, save, load,
minimap, view, toggle."""

import os
import unittest
from pathlib import Path

from tests.fixtures import GameTestBase


class TestHelpCommand(GameTestBase):
    def test_general_help(self):
        result = self.game.process_command("help")
        self.assertIn("Help", result)

    def test_help_for_specific_command(self):
        result = self.game.process_command("help look")
        self.assertIn("LOOK", result.upper())


class TestStopCommand(GameTestBase):
    def test_nothing_to_stop(self):
        result = self.game.process_command("stop")
        self.assertEqual("There is nothing to stop.", result)

    def test_stops_auto_travel(self):
        self.game.is_auto_traveling = True
        result = self.game.process_command("stop")
        self.assertEqual("", result)
        self.assertFalse(self.game.is_auto_traveling)


class TestQuitCommand(GameTestBase):
    def test_returns_to_title(self):
        result = self.game.process_command("quit")
        self.assertIn("title screen", result)
        self.assertEqual("title_screen", self.game.game_state)


class TestSaveAndLoadCommands(GameTestBase):
    TEST_SAVE = "test_system_commands_save.json"

    def tearDown(self):
        path = os.path.join("data", "saves", self.TEST_SAVE)
        if os.path.exists(path):
            try: os.remove(path)
            except OSError: pass
        super().tearDown()

    def test_save_with_explicit_filename(self):
        result = self.game.process_command(f"save {self.TEST_SAVE}")
        self.assertIn("saved", result)
        self.assertEqual(self.TEST_SAVE, self.game.current_save_file)

    def test_save_defaults_to_current_save_file(self):
        self.game.current_save_file = self.TEST_SAVE
        result = self.game.process_command("save")
        self.assertIn("saved", result)

    def test_load_missing_file_is_reported(self):
        result = self.game.process_command("load not_a_real_save_file")
        self.assertIn("not found", result)

    def test_load_round_trips_a_saved_game(self):
        self.game.process_command(f"save {self.TEST_SAVE}")
        result = self.game.process_command(f"load {self.TEST_SAVE}")
        self.assertIn("loaded", result)
        self.assertEqual("playing", self.game.game_state)


class TestMinimapCommand(GameTestBase):
    def test_toggle_off_then_on(self):
        # The "map" panel is registered in the right dock by default.
        off_result = self.game.process_command("minimap off")
        self.assertIn("disabled", off_result)
        again_off = self.game.process_command("minimap off")
        self.assertIn("already disabled", again_off)

        on_result = self.game.process_command("minimap on")
        self.assertIn("enabled", on_result)
        again_on = self.game.process_command("minimap on")
        self.assertIn("already enabled", again_on)

    def test_bare_toggle_flips_current_state(self):
        result = self.game.process_command("minimap")
        self.assertIn("disabled", result)  # was visible by default

    def test_invalid_argument_shows_usage(self):
        result = self.game.process_command("minimap sideways")
        self.assertIn("Usage", result)


class TestViewCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("view")
        self.assertIn("Usage", result)

    def test_list_shows_panel_states(self):
        result = self.game.process_command("view list")
        self.assertIn("inventory", result)
        self.assertIn("Left Dock", result)

    def test_unknown_panel_is_rejected(self):
        result = self.game.process_command("view not_a_real_panel on")
        self.assertIn("Unknown panel", result)

    def test_missing_action_shows_usage(self):
        result = self.game.process_command("view inventory")
        self.assertIn("Usage", result)

    def test_invalid_action_is_rejected(self):
        result = self.game.process_command("view inventory sideways")
        self.assertIn("Invalid action", result)

    def test_turning_off_then_on_a_panel(self):
        off_result = self.game.process_command("view inventory off")
        self.assertIn("hidden", off_result)
        already_off = self.game.process_command("view inventory off")
        self.assertIn("already hidden", already_off)

        on_result = self.game.process_command("view inventory on")
        self.assertIn("enabled", on_result)
        already_on = self.game.process_command("view inventory on")
        self.assertIn("already visible", already_on)


class TestToggleCommand(unittest.TestCase):
    """toggle_handler reads game.feature_profile/broadcast_global, which only
    exist on HeadlessServer -- it is a multiplayer-operator-only command with
    no single-player equivalent, so it needs the headless harness."""

    def test_usage_and_success_paths(self):
        from engine.commands.system import toggle_handler
        from engine.server.headless_server import HeadlessServer

        repo_root = Path(__file__).resolve().parents[3]
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(repo_root / "content_sets" / "fantasy_frontier"),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="toggle_test_player")
            server.execute_command(session.session_id, "char create Toggler")
            player = server.get_player_for_session(session.session_id)
            context = {"game": server, "world": server.world, "player": player}

            usage = toggle_handler([], context)
            self.assertIn("Usage", usage)

            bad = toggle_handler(["not_a_category", "on"], context)
            self.assertIn("Unknown category", bad)

            good = toggle_handler(["combat", "disabled"], context)
            self.assertIn("Set combat mode to disabled", good)
            self.assertEqual("disabled", server.feature_profile.combat_mode)
        finally:
            server.shutdown()
