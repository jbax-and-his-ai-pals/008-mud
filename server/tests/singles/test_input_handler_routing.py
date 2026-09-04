# tests/singles/test_input_handler_routing.py
"""Coverage for engine/core/input_handler.py's event routing across every
game_state (title, load menu, character creation, playing, game over),
including mouse handling, tab completion, history navigation, and the
UI-manager/zone interaction paths in _handle_playing_input."""

from types import SimpleNamespace
from unittest.mock import patch

import pygame

from tests.fixtures import GameTestBase
from engine.config import COMMAND_HISTORY_SIZE


class TestHandleEventRouting(GameTestBase):
    def test_unknown_state_is_a_no_op(self):
        handler = self.game.input_handler
        self.game.game_state = "some_unmapped_state"
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)
        handler.handle_event(event)  # must not raise

    def test_title_screen_routes_to_title_handler(self):
        handler = self.game.input_handler
        self.game.game_state = "title_screen"
        self.game.selected_title_option = 0
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)
        handler.handle_event(event)
        self.assertEqual(1, self.game.selected_title_option)


class TestCreationInputMouse(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "character_creation"
        self.game.creation_active_field = "class_list"
        self.game.available_classes = ["adventurer", "warrior"]
        self.game.selected_class_index = 0

    def test_click_name_box_focuses_name_input(self):
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(400, 120))
        self.handler._handle_creation_input(event)
        self.assertEqual("name_input", self.game.creation_active_field)

    def test_click_class_list_item_selects_it(self):
        # Second class item ("warrior") sits at content_y(220) + 1*40 = 260.
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(280, 265))
        self.handler._handle_creation_input(event)
        self.assertEqual(1, self.game.selected_class_index)
        self.assertEqual("class_list", self.game.creation_active_field)

    def test_click_background_defaults_to_class_list(self):
        self.game.creation_active_field = "name_input"
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))
        self.handler._handle_creation_input(event)
        self.assertEqual("class_list", self.game.creation_active_field)

    def test_right_click_is_ignored(self):
        self.game.creation_active_field = "class_list"
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(400, 120))
        self.handler._handle_creation_input(event)
        self.assertEqual("class_list", self.game.creation_active_field)

    def test_non_keydown_non_mousedown_event_is_ignored(self):
        event = pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1))
        self.handler._handle_creation_input(event)  # must not raise


class TestCreationInputKeyboard(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "character_creation"
        self.game.selected_class_index = 0
        self.game.creation_name_input = ""

    def _key(self, key, unicode=""):
        return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode)

    def test_tab_toggles_class_list_to_name_input(self):
        self.game.creation_active_field = "class_list"
        self.handler._handle_creation_input(self._key(pygame.K_TAB))
        self.assertEqual("name_input", self.game.creation_active_field)

    def test_tab_toggles_name_input_to_class_list(self):
        self.game.creation_active_field = "name_input"
        self.handler._handle_creation_input(self._key(pygame.K_TAB))
        self.assertEqual("class_list", self.game.creation_active_field)

    def test_class_list_up_wraps_around(self):
        self.game.available_classes = ["a", "b"]
        self.game.creation_active_field = "class_list"
        self.game.selected_class_index = 0
        self.handler._handle_creation_input(self._key(pygame.K_UP))
        self.assertEqual(1, self.game.selected_class_index)

    def test_class_list_down_advances(self):
        self.game.available_classes = ["a", "b"]
        self.game.creation_active_field = "class_list"
        self.game.selected_class_index = 0
        self.handler._handle_creation_input(self._key(pygame.K_DOWN))
        self.assertEqual(1, self.game.selected_class_index)

    def test_name_input_backspace(self):
        self.game.creation_active_field = "name_input"
        self.game.creation_name_input = "Bob"
        self.handler._handle_creation_input(self._key(pygame.K_BACKSPACE))
        self.assertEqual("Bo", self.game.creation_name_input)

    def test_name_input_appends_printable_char(self):
        self.game.creation_active_field = "name_input"
        self.handler._handle_creation_input(self._key(pygame.K_a, unicode="a"))
        self.assertEqual("a", self.game.creation_name_input)

    def test_name_input_ignores_control_keys(self):
        self.game.creation_active_field = "name_input"
        self.handler._handle_creation_input(self._key(pygame.K_ESCAPE, unicode="\x1b"))
        # ESCAPE is filtered from name text, but still triggers the global escape below.
        self.assertEqual("", self.game.creation_name_input)

    def test_name_input_enforces_max_length(self):
        self.game.creation_active_field = "name_input"
        self.game.creation_name_input = "x" * 20
        self.handler._handle_creation_input(self._key(pygame.K_a, unicode="a"))
        self.assertEqual(20, len(self.game.creation_name_input))

    def test_return_with_name_finalizes(self):
        self.game.selected_class_index = 0
        self.game.creation_name_input = "Hero"
        self.handler._handle_creation_input(self._key(pygame.K_RETURN))
        self.assertEqual("playing", self.game.game_state)

    def test_return_with_blank_name_does_not_finalize(self):
        self.game.creation_name_input = "   "
        self.handler._handle_creation_input(self._key(pygame.K_RETURN))
        self.assertEqual("character_creation", self.game.game_state)

    def test_escape_returns_to_title(self):
        self.handler._handle_creation_input(self._key(pygame.K_ESCAPE))
        self.assertEqual("title_screen", self.game.game_state)

    def test_unrecognized_active_field_skips_class_and_name_branches(self):
        self.game.creation_active_field = "something_else"
        self.game.creation_name_input = ""
        self.handler._handle_creation_input(self._key(pygame.K_a, unicode="a"))
        self.assertEqual("", self.game.creation_name_input)


class TestTitleInput(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "title_screen"

    def test_non_keydown_ignored(self):
        self.game.selected_title_option = 0
        self.handler._handle_title_input(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
        self.assertEqual(0, self.game.selected_title_option)

    def test_up_wraps_to_last_option(self):
        self.game.selected_title_option = 0
        self.handler._handle_title_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
        self.assertEqual(len(self.game.title_options) - 1, self.game.selected_title_option)

    def test_down_advances(self):
        self.game.selected_title_option = 0
        self.handler._handle_title_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
        self.assertEqual(1, self.game.selected_title_option)

    def test_return_selects_option(self):
        self.game.selected_title_option = 0
        self.handler._handle_title_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual("character_creation", self.game.game_state)

    def test_unhandled_key_is_a_no_op(self):
        self.game.selected_title_option = 0
        self.handler._handle_title_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
        self.assertEqual(0, self.game.selected_title_option)


class TestLoadInput(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "load_game_menu"
        self.game.available_saves = ["a.json", "b.json"]
        self.game.selected_load_option = 0

    def test_non_keydown_ignored(self):
        self.handler._handle_load_input(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
        self.assertEqual(0, self.game.selected_load_option)

    def test_up_wraps_to_last_option(self):
        self.handler._handle_load_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
        self.assertEqual(2, self.game.selected_load_option)  # len(saves)+1 - 1

    def test_down_advances(self):
        self.handler._handle_load_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
        self.assertEqual(1, self.game.selected_load_option)

    def test_return_selects_back_option(self):
        self.game.selected_load_option = 2  # "back" sentinel
        self.handler._handle_load_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual("title_screen", self.game.game_state)

    def test_escape_returns_to_title(self):
        self.handler._handle_load_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual("title_screen", self.game.game_state)

    def test_unhandled_key_is_a_no_op(self):
        self.handler._handle_load_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
        self.assertEqual(0, self.game.selected_load_option)


class TestPlayingInputKeyboard(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "playing"
        self.handler.input_text = ""
        self.handler.command_history = []
        self.handler.history_index = -1

    def _key(self, key, unicode=""):
        return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode)

    def test_return_with_text_processes_and_records_history(self):
        self.handler.input_text = "look"
        self.handler._handle_playing_input(self._key(pygame.K_RETURN))
        self.assertEqual(["look"], self.handler.command_history)
        self.assertEqual("", self.handler.input_text)
        self.assertEqual(-1, self.handler.history_index)

    def test_return_with_empty_text_does_nothing(self):
        self.handler.input_text = ""
        self.handler._handle_playing_input(self._key(pygame.K_RETURN))
        self.assertEqual([], self.handler.command_history)

    def test_history_size_cap_pops_oldest(self):
        self.handler.command_history = [f"cmd{i}" for i in range(COMMAND_HISTORY_SIZE)]
        self.handler.input_text = "newcmd"
        self.handler._handle_playing_input(self._key(pygame.K_RETURN))
        self.assertEqual(COMMAND_HISTORY_SIZE, len(self.handler.command_history))
        self.assertEqual("cmd1", self.handler.command_history[0])
        self.assertEqual("newcmd", self.handler.command_history[-1])

    def test_backspace_trims_input(self):
        self.handler.input_text = "abc"
        self.handler._handle_playing_input(self._key(pygame.K_BACKSPACE))
        self.assertEqual("ab", self.handler.input_text)

    def test_up_navigates_history(self):
        self.handler.command_history = ["look"]
        self.handler._handle_playing_input(self._key(pygame.K_UP))
        self.assertEqual("look", self.handler.input_text)

    def test_down_navigates_history(self):
        self.handler.command_history = ["look"]
        self.handler.history_index = 0
        self.handler._handle_playing_input(self._key(pygame.K_DOWN))
        self.assertEqual("", self.handler.input_text)

    def test_tab_triggers_completion(self):
        self.handler.input_text = "inv"
        self.handler._handle_playing_input(self._key(pygame.K_TAB))
        self.assertNotEqual("", self.handler.tab_completion_buffer)

    def test_pageup_scrolls(self):
        self.handler._handle_playing_input(self._key(pygame.K_PAGEUP))  # must not raise

    def test_pagedown_scrolls(self):
        self.handler._handle_playing_input(self._key(pygame.K_PAGEDOWN))  # must not raise

    def test_f1_toggles_debug_mode(self):
        self.handler._handle_playing_input(self._key(pygame.K_F1))
        self.assertTrue(self.game.debug_mode)

    def test_printable_char_appends(self):
        self.handler._handle_playing_input(self._key(pygame.K_x, unicode="x"))
        self.assertEqual("x", self.handler.input_text)

    def test_unmatched_non_printable_key_is_a_no_op(self):
        # F2 has no dedicated branch; a control-character unicode is non-printable.
        self.handler.input_text = "abc"
        self.handler._handle_playing_input(self._key(pygame.K_F2, unicode="\x01"))
        self.assertEqual("abc", self.handler.input_text)

    def test_mousewheel_scroll(self):
        self.game.renderer.text_formatter = SimpleNamespace(line_height_with_text=20)
        event = pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1)
        self.handler._handle_playing_input(event)  # must not raise


class TestPlayingInputMouse(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "playing"

    def test_ui_manager_consumes_event(self):
        with patch.object(self.game.ui_manager, "handle_event", return_value=True) as mock_handle:
            with patch.object(self.game, "process_command") as mock_process:
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_handle.assert_called_once()
                mock_process.assert_not_called()

    def test_left_click_on_zone_processes_its_command(self):
        zone = SimpleNamespace(command="look", data=None)
        with patch.object(self.game.renderer, "get_zone_at_pos", return_value=zone):
            with patch.object(self.game, "process_command") as mock_process:
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_process.assert_called_once_with("look")

    def test_right_click_on_zone_with_data_opens_context_menu(self):
        zone = SimpleNamespace(command="look", data={"some": "item"})
        with patch.object(self.game.renderer, "get_zone_at_pos", return_value=zone):
            with patch.object(self.game.ui_manager, "open_context_menu") as mock_open:
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_open.assert_called_once_with(zone.data, (10, 10))

    def test_right_click_on_zone_without_data_does_not_open_menu(self):
        zone = SimpleNamespace(command="look", data=None)
        with patch.object(self.game.renderer, "get_zone_at_pos", return_value=zone):
            with patch.object(self.game.ui_manager, "open_context_menu") as mock_open:
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_open.assert_not_called()

    def test_click_with_no_zone_is_a_no_op(self):
        with patch.object(self.game.renderer, "get_zone_at_pos", return_value=None):
            with patch.object(self.game, "process_command") as mock_process:
                event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_process.assert_not_called()

    def test_mousebuttondown_without_ui_consumption_is_a_no_op(self):
        with patch.object(self.game.ui_manager, "handle_event", return_value=False):
            with patch.object(self.game, "process_command") as mock_process:
                event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
                self.handler._handle_playing_input(event)
                mock_process.assert_not_called()

    def test_middle_click_on_zone_is_a_no_op(self):
        zone = SimpleNamespace(command="look", data={"some": "item"})
        with patch.object(self.game.renderer, "get_zone_at_pos", return_value=zone):
            with patch.object(self.game.ui_manager, "open_context_menu") as mock_open:
                with patch.object(self.game, "process_command") as mock_process:
                    event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=(10, 10))
                    self.handler._handle_playing_input(event)
                    mock_open.assert_not_called()
                    mock_process.assert_not_called()


class TestGameOverInput(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler
        self.game.game_state = "game_over"

    def test_non_keydown_ignored(self):
        with patch.object(self.game, "handle_respawn") as mock_respawn:
            self.handler._handle_game_over_input(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
            mock_respawn.assert_not_called()

    def test_r_respawns(self):
        with patch.object(self.game, "handle_respawn") as mock_respawn:
            self.handler._handle_game_over_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
            mock_respawn.assert_called_once()

    def test_q_quits_to_title(self):
        with patch.object(self.game, "quit_to_title") as mock_quit:
            self.handler._handle_game_over_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
            mock_quit.assert_called_once()

    def test_unhandled_key_is_a_no_op(self):
        with patch.object(self.game, "handle_respawn") as mock_respawn:
            with patch.object(self.game, "quit_to_title") as mock_quit:
                self.handler._handle_game_over_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
                mock_respawn.assert_not_called()
                mock_quit.assert_not_called()


class TestNavigateHistory(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler

    def test_empty_history_is_a_no_op(self):
        self.handler.command_history = []
        self.handler.history_index = -1
        self.handler._navigate_history(1)
        self.assertEqual(-1, self.handler.history_index)
        self.assertEqual("", self.handler.input_text)

    def test_direction_positive_clamps_at_oldest(self):
        self.handler.command_history = ["a", "b"]
        self.handler.history_index = 1
        self.handler._navigate_history(1)
        self.assertEqual(1, self.handler.history_index)

    def test_direction_non_positive_clamps_at_minus_one(self):
        self.handler.command_history = ["a", "b"]
        self.handler.history_index = -1
        self.handler._navigate_history(-1)
        self.assertEqual(-1, self.handler.history_index)
        self.assertEqual("", self.handler.input_text)


class TestTabCompletion(GameTestBase):
    def setUp(self):
        super().setUp()
        self.handler = self.game.input_handler

    def test_blank_input_is_a_no_op(self):
        self.handler.input_text = "   "
        self.handler.tab_completion_buffer = ""
        self.handler._handle_tab_completion()
        self.assertEqual("", self.handler.tab_completion_buffer)

    def test_no_matching_suggestions_leaves_index_unset(self):
        self.handler.input_text = "zzzznomatch"
        self.handler.tab_completion_buffer = ""
        self.handler.tab_suggestions = []
        self.handler._handle_tab_completion()
        self.assertEqual([], self.handler.tab_suggestions)
        self.assertEqual(-1, self.handler.tab_index)


if __name__ == "__main__":
    import unittest
    unittest.main()
