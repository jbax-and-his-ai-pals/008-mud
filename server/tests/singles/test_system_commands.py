# tests/singles/test_system_commands.py
"""Coverage for engine/commands/system.py: help, stop, quit, save, load,
minimap, view, toggle."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_no_game_reports_context_not_found(self):
        from engine.commands.system import quit_handler
        result = quit_handler([], {})
        self.assertIn("Game context not found", result)


class TestSaveAndLoadCommands(GameTestBase):
    TEST_SAVE = "test_system_commands_save.json"

    def tearDown(self):
        path = os.path.join(self.world.save_directory, self.TEST_SAVE)
        if os.path.exists(path):
            try: os.remove(path)
            except OSError: pass
        super().tearDown()

    def test_save_with_explicit_filename(self):
        result = self.game.process_command(f"save {self.TEST_SAVE}")
        self.assertIn("saved", result)
        self.assertEqual(self.TEST_SAVE, self.game.current_save_file)

    def test_save_uses_the_context_player(self):
        with patch.object(self.world, "save_game", return_value=True) as save_game:
            self.game.process_command(f"save {self.TEST_SAVE}")

        save_game.assert_called_once_with(self.TEST_SAVE, player=self.player)
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

    def test_save_no_player_reports_start_or_load(self):
        from engine.commands.system import save_handler
        result = save_handler([], {"world": self.world, "player": None})
        self.assertIn("start or load a game", result)

    def test_save_failure_is_reported(self):
        with patch.object(self.world, "save_game", return_value=False):
            result = self.game.process_command(f"save {self.TEST_SAVE}")
        self.assertIn("Error saving", result)

    def test_load_failure_is_reported(self):
        self.game.process_command(f"save {self.TEST_SAVE}")
        with patch.object(self.world, "load_save_game", return_value=(False, None, None)):
            result = self.game.process_command(f"load {self.TEST_SAVE}")
        self.assertIn("Error loading", result)

    def test_load_without_renderer_or_input_handler_skips_reset(self):
        # Calls load_handler directly (bypassing process_command) since
        # process_command itself unconditionally touches self.renderer
        # before/after dispatch, which would crash once it's None.
        from engine.commands.system import load_handler
        self.game.process_command(f"save {self.TEST_SAVE}")
        original_renderer = self.game.renderer
        original_input_handler = self.game.input_handler
        self.game.renderer = None
        self.game.input_handler = None
        try:
            context = {"world": self.world, "game": self.game}
            result = load_handler([self.TEST_SAVE], context)
        finally:
            self.game.renderer = original_renderer
            self.game.input_handler = original_input_handler
        self.assertIn("loaded", result)


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

    def test_no_game_reports_system_error(self):
        from engine.commands.system import toggle_minimap_handler
        result = toggle_minimap_handler([], {})
        self.assertIn("System error", result)

    def test_no_ui_manager_reports_unavailable(self):
        from engine.commands.system import toggle_minimap_handler
        from engine.server.headless_server import HeadlessServer

        repo_root = Path(__file__).resolve().parents[3]
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(repo_root / "content_sets" / "fantasy_frontier"),
        )
        try:
            result = toggle_minimap_handler([], {"game": server})
        finally:
            server.shutdown()
        self.assertIn("not available", result)

    def test_enable_failure_is_reported(self):
        self.game.process_command("minimap off")
        with patch.object(self.game.ui_manager, "add_panel_to_dock", return_value=False):
            result = self.game.process_command("minimap on")
        self.assertIn("Could not enable minimap", result)

    def test_disable_failure_is_reported(self):
        self.game.process_command("minimap on")
        with patch.object(self.game.ui_manager, "remove_panel", return_value=False):
            result = self.game.process_command("minimap off")
        self.assertIn("Could not disable minimap", result)


class TestViewCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("view")
        self.assertIn("Usage", result)

    def test_no_game_reports_context_missing(self):
        from engine.commands.system import view_panel_handler
        result = view_panel_handler([], {})
        self.assertIn("Game context missing", result)

    def test_no_ui_manager_reports_unavailable(self):
        from engine.commands.system import view_panel_handler
        from engine.server.headless_server import HeadlessServer

        repo_root = Path(__file__).resolve().parents[3]
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(repo_root / "content_sets" / "fantasy_frontier"),
        )
        try:
            result = view_panel_handler(["list"], {"game": server})
        finally:
            server.shutdown()
        self.assertIn("not available", result)

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

    def test_no_game_reports_context_not_found(self):
        from engine.commands.system import toggle_handler
        result = toggle_handler([], {})
        self.assertIn("Game context not found", result)

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
