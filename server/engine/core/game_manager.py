# engine/core/game_manager.py
import pygame
import sys
import os
import json
import time
from typing import List, Optional, Dict, Any

from engine.ai.ai_manager import AIManager
from engine.commands.command_system import CommandProcessor
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE, SCREEN_HEIGHT, SCREEN_WIDTH, TARGET_FPS,
    DEBUG_IGNORE_PLAYER_COMBAT, DEFAULT_SAVE_FILE
)
from engine.core.collection_manager import CollectionManager
from engine.core.knowledge_manager import KnowledgeManager
from engine.core.time_manager import TimeManager
from engine.core.weather_manager import WeatherManager
from engine.core.input_handler import InputHandler
from engine.ui.renderer import Renderer
from engine.world.world import World
from engine.server.content_set import load_content_set
from engine.utils.utils import format_name_for_display
from engine.ui.ui_manager import UIManager
from engine.ui.ui_element import UIPanel
from engine.ui.panel_content import (
    render_collections_content, render_stats_content, render_equipment_content, render_spells_content, 
    render_hostiles_content, render_friendlies_content, render_minimap_content,
    render_skills_content, render_quests_content, render_effects_content,
    render_inventory_content, render_topics_content
)
from engine.crafting.crafting_manager import CraftingManager
from engine.utils.logger import Logger

class GameManager:
    def __init__(self, content_set_path: str, save_file: str = DEFAULT_SAVE_FILE, save_directory: str | None = None):
        content_set, issues = load_content_set(content_set_path)
        errors = [issue.message for issue in issues if issue.severity == "error"]
        if content_set is None or errors:
            raise ValueError("GameManager requires a valid content set: " + "; ".join(errors))
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Pygame MUD")
        self.clock = pygame.time.Clock()

        self.world = World(content_set=content_set, save_directory=save_directory)
        self.world.game = self
        self.crafting_manager = CraftingManager(self.world)
        self.command_processor = CommandProcessor()
        self.time_manager = TimeManager(self.world)
        self.weather_manager = WeatherManager(self.world)
        self.renderer = Renderer(self.screen, self)
        self.input_handler = InputHandler(self, self.command_processor)
        self.ai_manager = AIManager(self)

        self.current_save_file = save_file
        self.game_state = "title_screen"
        self.debug_mode = False
        self.debug_ignore_player = DEBUG_IGNORE_PLAYER_COMBAT
        
        # UI Settings
        self.show_minimap = True
        self.show_inventory = False
        self.inventory_mode = "hybrid"
        
        # --- UI System ---
        self.ui_manager = UIManager()
        self.ui_manager.on_command_callback = self._handle_ui_command
        self._init_default_panels()

        # State for menus
        self.title_options = ["New Game", "Load Game", "Quit"]
        self.selected_title_option = 0
        self.available_saves: List[str] = []
        self.selected_load_option = 0

        # --- Character Creation State ---
        self.class_definitions: Dict[str, Any] = {}
        self.creation_active_field = "class_list" 
        self.available_classes: List[str] = []
        self.selected_class_index = 0
        self.creation_name_input = ""
        self._load_class_definitions()

        # State for auto-travel
        self.is_auto_traveling = False
        self.auto_travel_path = []
        self.auto_travel_guide = None
        self.auto_travel_timer = 0
        self.AUTO_TRAVEL_STEP_DELAY = 1000

        self.knowledge_manager = KnowledgeManager(self.world)
        self.collection_manager = CollectionManager(self.world)

    def _handle_ui_command(self, text: str) -> None:
        self.process_command(text)

    def _load_class_definitions(self):
        path = os.path.join(self.world.content_root, "player", "classes.json")
        
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    self.class_definitions = json.load(f)
                    self.available_classes = list(self.class_definitions.keys())
            except Exception as e:
                Logger.error("GameManager", f"Error loading classes: {e}")
                self.class_definitions = {}
        else:
            self.class_definitions = {
                "adventurer": {
                    "name": "Adventurer", "description": "A jack of all trades.",
                    "stats": {"strength": 10, "dexterity": 10, "intelligence": 10, "constitution": 10},
                    "equipment": {}, "inventory": [], "spells": []
                }
            }
            self.available_classes = ["adventurer"]

    def _init_default_panels(self):
        panels_def = [
            ("inventory", 180, "Inventory", render_inventory_content, "left"),
            ("stats", 200, "Stats", render_stats_content, "left"),
            ("equipment", 160, "Equipment", render_equipment_content, "left"),
            ("skills", 120, "Skills", render_skills_content, "left"),
            ("grimoire", 150, "Grimoire", render_spells_content, "left"),
            
            ("map", 250, "Map", render_minimap_content, "right"),
            ("hostiles", 150, "Hostiles", render_hostiles_content, "right"),
            ("people", 150, "People", render_friendlies_content, "right"),
            ("quests", 150, "Quests", render_quests_content, "right"),
            ("effects", 100, "Effects", render_effects_content, "right"),
            ("topics", 200, "Conversation", render_topics_content, "right"), 
            ("collections", 150, "Collections", render_collections_content, "right"),
        ]

        for pid, h, title, rend, side in panels_def:
            p = UIPanel(panel_id=pid, height=h, title=title, content_renderer=rend)
            self.ui_manager.register_panel(p)
            self.ui_manager.add_panel_to_dock(pid, side)

    def run(self):
        running = True
        while running:
            raw_dt = self.clock.tick(TARGET_FPS) / 1000.0
            dt = min(raw_dt, 0.1)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.VIDEORESIZE:
                    self._handle_resize(event)
                self.input_handler.handle_event(event)

            if self.game_state == "playing":
                self.update(dt)

            self.renderer.draw()
        
        pygame.quit()
        sys.exit()

    def update(self, dt: float):
        if self.is_auto_traveling:
            self._update_auto_travel()
            return 

        current_time_abs = time.time()

        ai_message = self.ai_manager.update()
        if ai_message:
            self.renderer.add_message(ai_message)
        
        time_change = self.time_manager.update(dt)
        if time_change:
            old_period, new_period = time_change
            season = self.time_manager.time_data.get("season", "summer")
            self.weather_manager.update_on_time_period_change(season)
            msg = self.time_manager.get_time_transition_message(old_period, new_period)
            if msg: self.renderer.add_message(msg)

        world_messages = self.world.update()
        for _location, msg in world_messages: self.renderer.add_message(msg)

        active_player = self.world.resolve_reference_player()
        if active_player and active_player.is_alive:
            player_messages = active_player.update(current_time_abs, dt)
            for msg in player_messages: self.renderer.add_message(msg)

        if active_player and not active_player.is_alive:
            self.game_state = "game_over"

    def process_command(self, text: str) -> Optional[str]:
        self.renderer.add_message(f"> {text}")
        context = {
            "game": self, 
            "world": self.world, 
            "command_processor": self.command_processor,
            "player": self.world.resolve_reference_player()
        }
        player = context["player"]
        command_result = None
        
        if not player:
            command_result = f"{FORMAT_ERROR}CRITICAL ERROR: Player is missing.{FORMAT_RESET}"
        elif not player.is_alive:
            cmd_word = text.strip().lower().split()[0]
            allowed_dead_commands = {"look", "l", "status", "st", "inventory", "i", "inv", "help", "h", "?", "quit", "q", "exit", "load"}
            if cmd_word in allowed_dead_commands:
                command_result = self.command_processor.process_input(text, context)
            else:
                command_result = f"{FORMAT_ERROR}You are dead. You cannot do that.{FORMAT_RESET}"
        else:
            command_result = self.command_processor.process_input(text, context)

        if command_result:
            self.renderer.add_message(command_result)
        self.renderer.scroll_offset = 0
        
        return command_result

    def start_new_game(self):
        self.game_state = "character_creation"
        self.creation_active_field = "class_list"
        self.creation_name_input = "Adventurer"
        self.selected_class_index = 0

    def finalize_new_game(self):
        self.world.initialize_new_world()
        self.time_manager.initialize_time()
        self.weather_manager = WeatherManager(self.world)
        
        if self.world.player:
            class_id = self.available_classes[self.selected_class_index]
            class_data = self.class_definitions.get(class_id)
            if not class_data:
                Logger.error("GameManager", "Failed to initialize new world properly! Returning to title.")
                self.game_state = "title_screen"
                return
            
            self.world.player.name = self.creation_name_input.strip() or "Adventurer"
            
            if class_data:
                self.world.player.apply_class_template(class_data)
            class_name = class_data.get("name", class_id.title())

            self.game_state = "playing"
            self.renderer.text_buffer = []
            welcome_message = f"{FORMAT_TITLE}Welcome to Pygame MUD, {self.world.player.name}!{FORMAT_RESET}\n"
            welcome_message += f"You begin your journey as a {class_name}.\n"
            welcome_message += f"Type 'help' to see available commands.\n\n{'='*40}\n\n{self.world.look()}"
            self.renderer.add_message(welcome_message)
            self.renderer.scroll_offset = 0
        else:
            Logger.error("GameManager", "Failed to initialize new world properly! Returning to title.")
            self.game_state = "title_screen"

    def load_selected_game(self):
        if self.selected_load_option < 0 or self.selected_load_option >= len(self.available_saves): return
        save_to_load = self.available_saves[self.selected_load_option]
        load_success, loaded_time_data, loaded_weather_data = self.world.load_save_game(save_to_load)
        if load_success and self.world.player:
            self.time_manager.apply_loaded_time_state(loaded_time_data)
            self.weather_manager.apply_loaded_weather_state(loaded_weather_data)
            self.current_save_file = save_to_load
            self.game_state = "playing"
            self.renderer.text_buffer = []
            welcome_message = f"{FORMAT_TITLE}Welcome back!{FORMAT_RESET}\n(Loaded game: {self.current_save_file})\n\n{'='*40}\n\n{self.world.look()}"
            self.renderer.add_message(welcome_message)
            self.renderer.scroll_offset = 0
        else:
            Logger.error("GameManager", f"Failed to load '{save_to_load}'. Returning to title.")
            # World() requires a content set; reuse the currently selected one
            # instead of constructing an invalid empty World.
            self.world = World(content_set=self.world.content_set)
            self.world.game = self
            self.game_state = "title_screen"

    def handle_respawn(self):
        if self.game_state != "game_over" or not self.world.player: return
        self.world.player.respawn()
        self.world.current_region_id = self.world.player.respawn_region_id
        self.world.current_room_id = self.world.player.respawn_room_id
        self.renderer.text_buffer = [f"{FORMAT_HIGHLIGHT}You feel your spirit return to your body...{FORMAT_RESET}\n"]
        self.renderer.add_message(self.world.look())
        self.game_state = "playing"
        self.input_handler.input_text = ""

    def quit_to_title(self):
        self.renderer.text_buffer = []
        self.renderer.scroll_offset = 0
        self.input_handler.input_text = ""
        self.input_handler.command_history = []
        self.input_handler.history_index = -1
        self.game_state = "title_screen"

    def select_title_option(self):
        selected = self.title_options[self.selected_title_option]
        if selected == "New Game": self.start_new_game()
        elif selected == "Load Game": self._update_available_saves(); self.game_state = "load_game_menu"; self.selected_load_option = 0
        elif selected == "Quit": pygame.event.post(pygame.event.Event(pygame.QUIT))

    def select_load_option(self):
        if self.selected_load_option == len(self.available_saves):
            self.game_state = "title_screen"
        elif self.available_saves and 0 <= self.selected_load_option < len(self.available_saves):
            self.load_selected_game()

    def _update_available_saves(self):
        self.available_saves = []
        save_directory = self.world.save_directory
        if not os.path.isdir(save_directory): return
        try:
            self.available_saves = sorted([fname for fname in os.listdir(save_directory) if fname.lower().endswith(".json")])
        except Exception as e:
            Logger.error("GameManager", f"Error scanning save directory '{save_directory}': {e}")
            
    def toggle_debug_mode(self):
        self.debug_mode = not self.debug_mode
        if self.game_state == "playing":
            msg = f"{FORMAT_HIGHLIGHT}Debug mode {'enabled' if self.debug_mode else 'disabled'}.{FORMAT_RESET}"
            self.renderer.add_message(msg)

    def _handle_resize(self, event):
        new_width, new_height = max(800, event.w), max(600, event.h)
        self.screen = pygame.display.set_mode((new_width, new_height), pygame.RESIZABLE)
        self.renderer.screen = self.screen

    def start_auto_travel(self, path: List[str], guide_npc):
        self.is_auto_traveling = True
        self.auto_travel_path = path
        self.auto_travel_guide = guide_npc
        self.auto_travel_timer = self.AUTO_TRAVEL_STEP_DELAY

    def stop_auto_travel(self, reason: str = "cancelled"):
        if self.auto_travel_guide:
            if reason == "cancelled":
                self.renderer.add_message(f"{self.auto_travel_guide.name} stops guiding you.")
        self.is_auto_traveling = False
        self.auto_travel_path = []
        self.auto_travel_guide = None
        self.auto_travel_timer = 0
        if reason == "cancelled":
            self.renderer.add_message(f"{FORMAT_HIGHLIGHT}Auto-travel stopped.{FORMAT_RESET}")

    def _update_auto_travel(self):
        if not self.world.player or not self.auto_travel_guide or not self.auto_travel_guide.is_alive or not self.world.player.is_alive:
            self.stop_auto_travel("interrupted")
            return

        self.auto_travel_timer -= self.clock.get_time()
        if self.auto_travel_timer <= 0:
            if not self.auto_travel_path:
                arrival_message = self.auto_travel_guide.dialog.get("arrival_handoff", "We're here.")
                self.renderer.add_message(f"{self.auto_travel_guide.name} says: \"{arrival_message}\"")
                self.stop_auto_travel("arrived")
                return

            direction = self.auto_travel_path.pop(0)
            move_result = self.world.change_room(direction, player=self.world.player)
            self.renderer.add_message(move_result)
            
            self.auto_travel_guide.current_region_id = self.world.player.current_region_id
            self.auto_travel_guide.current_room_id = self.world.player.current_room_id
            
            formatted_guide_name = format_name_for_display(self.world.player, self.auto_travel_guide, start_of_sentence=True)
            self.renderer.add_message(f"{formatted_guide_name} leads the way.")
            self.auto_travel_timer = self.AUTO_TRAVEL_STEP_DELAY
