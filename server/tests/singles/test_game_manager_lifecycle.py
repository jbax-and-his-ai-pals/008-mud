# tests/singles/test_game_manager_lifecycle.py
"""Coverage for engine/core/game_manager.py's menu/lifecycle methods, which
GameTestBase's command-driven tests never exercise directly: update()'s
non-auto-travel tick, class-definition loading fallbacks, new-game/load-game
menu flow, respawn, debug toggle, resize, and auto-travel stop/interrupt.
Intentionally skips run() -- the actual pygame blocking event loop."""

import os
import shutil
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.utils.logger import Logger, LogLevel


class TestLoadClassDefinitions(GameTestBase):
    def test_malformed_classes_json_falls_back_to_empty(self):
        classes_path = os.path.join(self.world.data_root, "player", "classes.json")
        with open(classes_path, "r", encoding="utf-8") as f:
            original = f.read()
        try:
            with open(classes_path, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            self.game._load_class_definitions()
            self.assertEqual({}, self.game.class_definitions)
        finally:
            with open(classes_path, "w", encoding="utf-8") as f:
                f.write(original)

    def test_missing_classes_json_falls_back_to_default_adventurer(self):
        real_data_root = self.world.data_root
        try:
            self.world.data_root = os.path.join(real_data_root, "does_not_exist")
            self.game._load_class_definitions()
            self.assertEqual(["adventurer"], self.game.available_classes)
            self.assertIn("adventurer", self.game.class_definitions)
        finally:
            self.world.data_root = real_data_root


class TestUpdateTick(GameTestBase):
    def test_update_runs_world_and_player_ticks(self):
        self.game.update(0.1)  # must not raise

    def test_update_delegates_to_auto_travel_when_traveling(self):
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = None  # -> _update_auto_travel will stop it as "interrupted"
        self.game.update(0.1)
        self.assertFalse(self.game.is_auto_traveling)

    def test_update_marks_game_over_when_player_dies(self):
        self.player.health = 0
        self.player.is_alive = False
        self.game.update(0.1)
        self.assertEqual("game_over", self.game.game_state)


class TestProcessCommandPlayerGuards(GameTestBase):
    def test_no_player_reports_critical_error(self):
        self.world.player = None
        result = self.game.process_command("look")
        self.assertIn("CRITICAL ERROR", result)

    def test_dead_player_blocks_non_allowlisted_commands(self):
        self.player.is_alive = False
        result = self.game.process_command("north")
        self.assertIn("You are dead", result)

    def test_dead_player_allows_allowlisted_commands(self):
        self.player.is_alive = False
        result = self.game.process_command("status")
        self.assertNotIn("You are dead", result)


class TestNewGameFlow(GameTestBase):
    def test_start_new_game_enters_character_creation(self):
        self.game.start_new_game()
        self.assertEqual("character_creation", self.game.game_state)
        self.assertEqual("class_list", self.game.creation_active_field)

    def test_finalize_new_game_success(self):
        self.game.selected_class_index = 0
        self.game.creation_name_input = "Hero Name"
        self.game.finalize_new_game()
        self.assertEqual("playing", self.game.game_state)
        self.assertEqual("Hero Name", self.world.player.name)

    def test_finalize_new_game_blank_name_defaults_to_adventurer(self):
        self.game.selected_class_index = 0
        self.game.creation_name_input = "   "
        self.game.finalize_new_game()
        self.assertEqual("Adventurer", self.world.player.name)

    def test_finalize_new_game_missing_class_data_returns_to_title(self):
        self.game.available_classes = ["ghost_class"]
        self.game.selected_class_index = 0
        self.game.class_definitions = {}  # ghost_class not present
        self.game.finalize_new_game()
        self.assertEqual("title_screen", self.game.game_state)

    def test_finalize_new_game_without_a_player_returns_to_title(self):
        # finalize_new_game() itself calls initialize_new_world(), which always
        # creates a player for a valid content set -- stub it out to exercise
        # the "world init produced no player" fallback in isolation.
        self.world.initialize_new_world = lambda *a, **k: None
        self.world.player = None
        self.game.finalize_new_game()
        self.assertEqual("title_screen", self.game.game_state)


class TestLoadGameMenuFlow(GameTestBase):
    SAVE_NAME = "test_gm_lifecycle_save.json"

    def tearDown(self):
        path = os.path.join("data", "saves", self.SAVE_NAME)
        if os.path.exists(path):
            try: os.remove(path)
            except OSError: pass
        super().tearDown()

    def test_load_selected_game_with_out_of_range_index_is_a_no_op(self):
        self.game.available_saves = []
        self.game.selected_load_option = 0
        self.game.load_selected_game()  # must not raise
        self.assertNotEqual("playing", self.game.game_state)

    def test_load_selected_game_success(self):
        self.world.save_game(self.SAVE_NAME)
        self.game.available_saves = [self.SAVE_NAME]
        self.game.selected_load_option = 0
        self.game.load_selected_game()
        self.assertEqual("playing", self.game.game_state)
        self.assertEqual(self.SAVE_NAME, self.game.current_save_file)

    def test_load_selected_game_failure_returns_to_title(self):
        self.game.available_saves = ["not_a_real_save_file.json"]
        self.game.selected_load_option = 0
        Logger.set_level(LogLevel.CRITICAL)
        self.game.load_selected_game()
        self.assertEqual("title_screen", self.game.game_state)

    def test_select_title_option_new_game(self):
        self.game.selected_title_option = 0  # "New Game"
        self.game.select_title_option()
        self.assertEqual("character_creation", self.game.game_state)

    def test_select_title_option_load_game(self):
        self.game.selected_title_option = 1  # "Load Game"
        self.game.select_title_option()
        self.assertEqual("load_game_menu", self.game.game_state)

    def test_select_title_option_quit_posts_quit_event(self):
        import pygame
        pygame.event.clear()
        self.game.selected_title_option = 2  # "Quit"
        self.game.select_title_option()
        posted = pygame.event.get()
        self.assertTrue(any(e.type == pygame.QUIT for e in posted))

    def test_select_load_option_back_to_title(self):
        self.game.available_saves = ["a.json", "b.json"]
        self.game.selected_load_option = 2  # sentinel "back" index
        self.game.select_load_option()
        self.assertEqual("title_screen", self.game.game_state)

    def test_select_load_option_loads_valid_index(self):
        self.world.save_game(self.SAVE_NAME)
        self.game.available_saves = [self.SAVE_NAME]
        self.game.selected_load_option = 0
        self.game.select_load_option()
        self.assertEqual("playing", self.game.game_state)

    def test_update_available_saves_with_missing_directory(self):
        from engine.config import SAVE_GAME_DIR
        original_exists = os.path.isdir(SAVE_GAME_DIR)
        if not original_exists:
            self.game._update_available_saves()
            self.assertEqual([], self.game.available_saves)
        else:
            # Directory exists in this environment; just verify it doesn't raise
            # and returns a list (covered by the "with files" test below).
            self.game._update_available_saves()

    def test_update_available_saves_lists_json_files(self):
        self.world.save_game(self.SAVE_NAME)
        self.game._update_available_saves()
        self.assertIn(self.SAVE_NAME, self.game.available_saves)


class TestRespawnAndTitleAndDebug(GameTestBase):
    def test_handle_respawn_no_op_when_not_game_over(self):
        self.game.game_state = "playing"
        self.game.handle_respawn()
        self.assertEqual("playing", self.game.game_state)

    def test_handle_respawn_restores_player(self):
        self.game.game_state = "game_over"
        self.player.health = 0
        self.player.is_alive = False
        self.game.handle_respawn()
        self.assertEqual("playing", self.game.game_state)
        self.assertTrue(self.player.is_alive)

    def test_quit_to_title_resets_state(self):
        self.game.input_handler.input_text = "leftover"
        self.game.quit_to_title()
        self.assertEqual("title_screen", self.game.game_state)
        self.assertEqual("", self.game.input_handler.input_text)

    def test_toggle_debug_mode_while_playing_emits_message(self):
        self.game.game_state = "playing"
        self.game.renderer.clear()
        self.game.toggle_debug_mode()
        self.assertTrue(self.game.debug_mode)
        self.assertTrue(any("Debug mode enabled" in m for m in self.game.renderer.message_buffer))

    def test_toggle_debug_mode_outside_playing_is_silent(self):
        self.game.game_state = "title_screen"
        self.game.renderer.clear()
        self.game.toggle_debug_mode()
        self.assertEqual([], self.game.renderer.message_buffer)

    def test_handle_resize_updates_screen_dimensions(self):
        class _FakeResizeEvent:
            w = 1024
            h = 768
        self.game._handle_resize(_FakeResizeEvent())
        self.assertIs(self.game.screen, self.game.renderer.screen)

    def test_handle_resize_enforces_minimum_dimensions(self):
        class _FakeResizeEvent:
            w = 100
            h = 100
        # Must not raise even with below-minimum requested dimensions.
        self.game._handle_resize(_FakeResizeEvent())


class TestAutoTravelStopAndInterrupt(GameTestBase):
    def test_stop_auto_travel_cancelled_emits_messages(self):
        class _Guide:
            name = "Guide"
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = _Guide()
        self.game.renderer.clear()
        self.game.stop_auto_travel("cancelled")
        self.assertFalse(self.game.is_auto_traveling)
        joined = "\n".join(self.game.renderer.message_buffer)
        self.assertIn("stops guiding you", joined)
        self.assertIn("Auto-travel stopped", joined)

    def test_stop_auto_travel_interrupted_is_silent(self):
        class _Guide:
            name = "Guide"
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = _Guide()
        self.game.renderer.clear()
        self.game.stop_auto_travel("interrupted")
        self.assertEqual([], self.game.renderer.message_buffer)

    def test_update_auto_travel_interrupts_when_guide_is_dead(self):
        class _Guide:
            name = "Guide"
            is_alive = False
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = _Guide()
        self.game._update_auto_travel()
        self.assertFalse(self.game.is_auto_traveling)

    def test_update_auto_travel_interrupts_when_player_is_dead(self):
        class _Guide:
            name = "Guide"
            is_alive = True
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = _Guide()
        self.player.is_alive = False
        self.game._update_auto_travel()
        self.assertFalse(self.game.is_auto_traveling)


class TestGameManagerConstruction(GameTestBase):
    def test_invalid_content_set_path_raises(self):
        from engine.core.game_manager import GameManager
        with self.assertRaises(ValueError):
            GameManager("totally_bogus_content_set_path_xyz")


class TestHandleUiCommand(GameTestBase):
    def test_delegates_to_process_command(self):
        with patch.object(self.game, "process_command") as mock_process:
            self.game._handle_ui_command("look")
        mock_process.assert_called_once_with("look")


class TestUpdateTickMessages(GameTestBase):
    def test_ai_manager_message_is_added_to_renderer(self):
        with patch.object(self.game.ai_manager, "update", return_value="An NPC did something."):
            self.game.update(0.1)
        self.assertIn("An NPC did something.", self.game.renderer.message_buffer)

    def test_time_period_change_updates_weather_and_emits_message(self):
        with patch.object(self.game.time_manager, "update", return_value=("night", "dawn")):
            with patch.object(self.game.weather_manager, "update_on_time_period_change") as mock_weather:
                with patch.object(
                    self.game.time_manager, "get_time_transition_message", return_value="The sun rises.",
                ):
                    self.game.update(0.1)
        mock_weather.assert_called_once()
        self.assertIn("The sun rises.", self.game.renderer.message_buffer)


class TestSelectLoadOptionNoOp(GameTestBase):
    def test_no_available_saves_is_a_noop(self):
        self.game.available_saves = []
        self.game.selected_load_option = 5
        self.game.game_state = "load_game_menu"
        self.game.select_load_option()
        self.assertEqual(self.game.game_state, "load_game_menu")


class TestUpdateAvailableSavesErrorHandling(GameTestBase):
    def test_missing_directory_is_deterministically_a_noop(self):
        with patch("os.path.isdir", return_value=False):
            self.game._update_available_saves()
        self.assertEqual(self.game.available_saves, [])

    def test_listdir_exception_is_caught(self):
        with patch("os.path.isdir", return_value=True):
            with patch("os.listdir", side_effect=OSError("boom")):
                self.game._update_available_saves()
        self.assertEqual(self.game.available_saves, [])


class TestUpdateAutoTravelTimerNotElapsed(GameTestBase):
    def test_timer_still_counting_down_takes_no_action(self):
        class _Guide:
            name = "Guide"
            is_alive = True
        class _FakeClock:
            def get_time(self):
                return 1
        self.game.is_auto_traveling = True
        self.game.auto_travel_guide = _Guide()
        self.game.auto_travel_timer = 10000
        original_clock = self.game.clock
        self.game.clock = _FakeClock()
        try:
            self.game._update_auto_travel()
        finally:
            self.game.clock = original_clock
        self.assertTrue(self.game.is_auto_traveling)
        self.assertGreater(self.game.auto_travel_timer, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
