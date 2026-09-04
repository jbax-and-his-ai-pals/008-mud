# engine/core/input_handler.py
"""
Handles all raw user input from Pygame and translates it into game actions.
Updated to handle mouse clicks for clickable text and character creation.
"""
import pygame
from typing import TYPE_CHECKING, List

from engine.commands.command_system import CommandProcessor
from engine.config import COMMAND_HISTORY_SIZE, SCROLL_SPEED

if TYPE_CHECKING:
    from engine.core.game_manager import GameManager


class InputHandler:
    def __init__(self, game: 'GameManager', command_processor: CommandProcessor):
        self.game = game
        self.command_processor = command_processor

        self.input_text = ""
        self.command_history: List[str] = []
        self.history_index = -1
        self.tab_completion_buffer = ""
        self.tab_suggestions: List[str] = []
        self.tab_index = -1

    def handle_event(self, event: pygame.event.Event):
        """Main event handling router based on the current game state."""
        state_handler_map = {
            "title_screen": self._handle_title_input,
            "load_game_menu": self._handle_load_input,
            "playing": self._handle_playing_input,
            "game_over": self._handle_game_over_input,
            "character_creation": self._handle_creation_input
        }
        handler = state_handler_map.get(self.game.game_state)
        if handler:
            handler(event)

    def _handle_creation_input(self, event):
        game = self.game

        # --- Mouse Handling ---
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            sw = game.renderer.layout.get("screen_width", 800)
            
            # 1. Check Name Box Click
            name_box_width = 400
            name_box_rect = pygame.Rect((sw - name_box_width)//2, 100, name_box_width, 50)
            
            if name_box_rect.collidepoint(event.pos):
                game.creation_active_field = "name_input"
                return

            # 2. Check Class List Clicks
            content_y = 220
            list_width = 250
            list_x = (sw // 2) - list_width - 20
            
            for i, class_id in enumerate(game.available_classes):
                item_y = content_y + (i * 40)
                # Area matches visual list item
                item_rect = pygame.Rect(list_x - 10, item_y - 5, list_width + 20, 30)
                
                if item_rect.collidepoint(event.pos):
                    game.selected_class_index = i
                    game.creation_active_field = "class_list"
                    return

            # Clicked background -> Default to class list
            game.creation_active_field = "class_list"
            return

        # --- Keyboard Handling ---
        if event.type != pygame.KEYDOWN: return
        
        # Navigation
        if event.key == pygame.K_TAB:
            # Toggle Focus
            if game.creation_active_field == "class_list":
                game.creation_active_field = "name_input"
            else:
                game.creation_active_field = "class_list"
            return

        # Interaction based on focus
        if game.creation_active_field == "class_list":
            if event.key == pygame.K_UP:
                game.selected_class_index = (game.selected_class_index - 1) % len(game.available_classes)
            elif event.key == pygame.K_DOWN:
                game.selected_class_index = (game.selected_class_index + 1) % len(game.available_classes)
        
        elif game.creation_active_field == "name_input":
            if event.key == pygame.K_BACKSPACE:
                game.creation_name_input = game.creation_name_input[:-1]
            else:
                # Filter control keys
                if event.key not in [pygame.K_TAB, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE]:
                    if event.unicode.isprintable() and len(game.creation_name_input) < 20:
                        game.creation_name_input += event.unicode
        
        # Global Creation Keys
        if event.key in [pygame.K_RETURN, pygame.K_KP_ENTER]:
            # Only finalize if name is not empty
            if game.creation_name_input.strip():
                game.finalize_new_game()
        elif event.key == pygame.K_ESCAPE:
            game.game_state = "title_screen"

    def _handle_title_input(self, event):
        if event.type != pygame.KEYDOWN: return
        if event.key == pygame.K_UP: self.game.selected_title_option = (self.game.selected_title_option - 1) % len(self.game.title_options)
        elif event.key == pygame.K_DOWN: self.game.selected_title_option = (self.game.selected_title_option + 1) % len(self.game.title_options)
        elif event.key in [pygame.K_RETURN, pygame.K_KP_ENTER]:
            self.game.select_title_option()

    def _handle_load_input(self, event):
        if event.type != pygame.KEYDOWN: return
        num_options = len(self.game.available_saves) + 1
        if event.key == pygame.K_UP: self.game.selected_load_option = (self.game.selected_load_option - 1 + num_options) % num_options
        elif event.key == pygame.K_DOWN: self.game.selected_load_option = (self.game.selected_load_option + 1) % num_options
        elif event.key in [pygame.K_RETURN, pygame.K_KP_ENTER]:
            self.game.select_load_option()
        elif event.key == pygame.K_ESCAPE:
            self.game.game_state = "title_screen"

    def _handle_playing_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in [pygame.K_RETURN, pygame.K_KP_ENTER]:                
                if self.input_text:
                    self.game.process_command(self.input_text)
                    self.command_history.append(self.input_text)
                    if len(self.command_history) > COMMAND_HISTORY_SIZE:
                        self.command_history.pop(0)
                    self.history_index = -1
                    self.input_text = ""
                    self.tab_completion_buffer = ""
            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
                self.tab_completion_buffer = ""
            elif event.key == pygame.K_UP:
                self._navigate_history(1)
            elif event.key == pygame.K_DOWN:
                self._navigate_history(-1)
            elif event.key == pygame.K_TAB:
                self._handle_tab_completion()
            elif event.key == pygame.K_PAGEUP:
                self.game.renderer.scroll(self.game.renderer.layout["text_area"]["height"] // 2)
            elif event.key == pygame.K_PAGEDOWN:
                self.game.renderer.scroll(-self.game.renderer.layout["text_area"]["height"] // 2)
            elif event.key == pygame.K_F1:
                self.game.toggle_debug_mode()
            else:
                if event.unicode.isprintable():
                    self.input_text += event.unicode
                    self.tab_completion_buffer = ""
        
        elif event.type == pygame.MOUSEWHEEL:
            scroll_amount_pixels = SCROLL_SPEED * self.game.renderer.text_formatter.line_height_with_text * event.y
            self.game.renderer.scroll(scroll_amount_pixels)

        # --- MOUSE HANDLING ---
        if event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION]:
            
            # 1. UI Manager Priority (Drags & Context Menu clicks)
            if self.game.ui_manager.handle_event(event):
                return

            # 2. Interaction Logic
            if event.type == pygame.MOUSEBUTTONUP:
                zone = self.game.renderer.get_zone_at_pos(event.pos)
                
                if zone:
                    if event.button == 1: # Left Click
                        self.game.process_command(zone.command)
                    elif event.button == 3: # Right Click
                        # Open Context Menu if data exists
                        if zone.data:
                            self.game.ui_manager.open_context_menu(zone.data, event.pos)

    def _handle_game_over_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.game.handle_respawn()
            elif event.key == pygame.K_q:
                self.game.quit_to_title()

    def _navigate_history(self, direction: int):
        if not self.command_history: return
        if direction > 0: self.history_index = min(self.history_index + 1, len(self.command_history) - 1)
        else: self.history_index = max(self.history_index - 1, -1)
        self.input_text = self.command_history[-(self.history_index + 1)] if self.history_index >= 0 else ""
        self.tab_completion_buffer = ""

    def _handle_tab_completion(self):
        if not self.input_text.strip(): return
        
        # If buffer is empty or suggestions cleared, it's a new completion cycle
        if not self.tab_completion_buffer or not self.tab_suggestions:
            self.tab_completion_buffer = self.input_text.strip()
            self.tab_suggestions = self.command_processor.get_command_suggestions(self.tab_completion_buffer)
            self.tab_index = -1
            
        if self.tab_suggestions:
            self.tab_index = (self.tab_index + 1) % len(self.tab_suggestions)
            self.input_text = self.tab_suggestions[self.tab_index]
