# engine/ui/renderer.py
"""
Handles all rendering for the game, including UI panels, text, and game states.
Optimized with Surface caching and clickable text support.
"""
import pygame
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from engine.config import *
from engine.ui import panels
from engine.ui import minimap
from engine.ui.floating_text import FloatingText
from engine.ui.inventory_menu import InventoryMenu
from engine.utils.text_formatter import TextFormatter, ClickableZone
from engine.magic.spell_registry import get_spell
import engine.ui.screens as screens  # Assumes screens.py exists from previous step

if TYPE_CHECKING:
    from engine.core.game_manager import GameManager


class Renderer:
    def __init__(self, screen: pygame.Surface, game: 'GameManager'):
        self.screen = screen
        self.game = game
        self.font = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE, bold=False)
        self.title_font = pygame.font.SysFont(FONT_FAMILY, int(FONT_SIZE * 1.5), bold=True)
        self.selected_font = pygame.font.SysFont(FONT_FAMILY, FONT_SIZE, bold=True)
        
        self.layout: Dict[str, Any] = {}
        self._last_screen_size = (0, 0)
        self._last_minimap_state: Optional[bool] = None
        
        self.scroll_offset = 0
        self.total_rendered_height = 0
        self.text_buffer: List[str] = []
        
        self._cached_text_surface: Optional[pygame.Surface] = None
        self._text_dirty = True
        
        # Store hotspots relative to the cached surface
        self._text_area_hotspots: List[ClickableZone] = []
        # Store hotspots relative to the screen (Panels)
        self._static_hotspots: List[ClickableZone] = []
        
        self.cursor_visible = True
        self.cursor_timer = 0
        
        self.inventory_menu = InventoryMenu(game)

        self.text_formatter = TextFormatter(
            font=self.font,
            screen_width=SCREEN_WIDTH,
            colors=DEFAULT_COLORS,
            margin=10,
            line_spacing=LINE_SPACING
        )

        self.floating_texts: List[FloatingText] = []

    def add_floating_text(self, text: str, x: int, y: int, color: tuple):
        """Adds a floating text effect to the queue."""
        self.floating_texts.append(FloatingText(text, x, y, color))

    def get_zone_at_pos(self, screen_pos: tuple[int, int]) -> Optional[ClickableZone]:
        """
        Returns the ClickableZone at the screen position.
        """
        mx, my = screen_pos

        # 1. Check Static Hotspots (Panels)
        for zone in self._static_hotspots:
            if zone.rect.collidepoint(mx, my):
                return zone

        # 2. Check Text Area Hotspots
        if not self.layout or "text_area" not in self.layout: return None
            
        text_area = self.layout["text_area"]
        tx, ty, tw, th = text_area["x"], text_area["y"], text_area["width"], text_area["height"]

        if not (tx <= mx <= tx + tw and ty <= my <= ty + th): return None

        content_height = self.total_rendered_height
        visible_height = th
        source_y_start = max(0, content_height - visible_height - self.scroll_offset)
        relative_mouse_y = my - ty
        cache_y = source_y_start + relative_mouse_y
        cache_x = mx - tx

        for zone in self._text_area_hotspots:
            if zone.rect.collidepoint(cache_x, cache_y):
                return zone
        
        return None

    def calculate_layout(self):
        """
        Calculates UI panel positions based on screen size.
        Only runs if the screen size has changed.
        """
        current_width, current_height = self.screen.get_size()
        
        # Optimization: Don't recalculate if nothing changed
        if (current_width, current_height) == self._last_screen_size and self.layout:
            return

        self._last_screen_size = (current_width, current_height)
        self._text_dirty = True 

        side_panel_width = SIDE_PANEL_WIDTH
        padding = STATUS_PANEL_PADDING
        time_bar_height = 30
        input_area_height = INPUT_HEIGHT
        
        # Structural Margins
        layout_margin = 5 
        content_margin = self.text_formatter.margin
        
        # Y Coordinates
        time_bar_y = 0
        panels_top_y = time_bar_y + time_bar_height + layout_margin
        
        # Side Panels extend to the bottom minus the small margin
        side_panels_bottom_y = current_height - layout_margin
        panels_available_height = max(50, side_panels_bottom_y - panels_top_y)
        
        # 1. Left Dock Bounds
        left_panel_rect = pygame.Rect(layout_margin, panels_top_y, side_panel_width, panels_available_height)
        
        # 2. Right Dock Bounds
        right_x = current_width - side_panel_width - layout_margin
        right_status_rect = pygame.Rect(right_x, panels_top_y, side_panel_width, panels_available_height)
        
        # 3. Center Area Geometry
        center_area_x_start = left_panel_rect.right + layout_margin
        center_area_x_end = right_status_rect.left - layout_margin
        center_area_width = max(100, center_area_x_end - center_area_x_start)
        
        # Input Area (Bottom of Center Column)
        input_rect = pygame.Rect(
            center_area_x_start, 
            side_panels_bottom_y - input_area_height, 
            center_area_width, 
            input_area_height
        )
        
        # Room Info Panel (Fixed Height Top Center)
        target_room_panel_height = 300
        min_text_area_height = 100
        
        center_available_height = input_rect.top - panels_top_y - layout_margin
        actual_room_panel_height = max(30, min(target_room_panel_height, center_available_height - min_text_area_height))
        
        room_panel_rect = pygame.Rect(center_area_x_start, panels_top_y, center_area_width, actual_room_panel_height)
        
        # Text Log Area (Remaining Center Height)
        text_area_y = room_panel_rect.bottom + layout_margin
        text_area_bottom = input_rect.top - layout_margin
        text_area_height = max(min_text_area_height, text_area_bottom - text_area_y)
        
        text_area_rect = pygame.Rect(center_area_x_start, text_area_y, center_area_width, text_area_height)
        
        self.layout = {
            "screen_width": current_width,
            "screen_height": current_height,
            "time_bar": {"height": time_bar_height, "y": time_bar_y},
            "input_area": {
                "x": input_rect.x, "y": input_rect.y, 
                "width": input_rect.width, "height": input_rect.height
            },
            "left_status_panel": {
                "x": left_panel_rect.x, "y": left_panel_rect.y, 
                "width": left_panel_rect.width, "height": left_panel_rect.height
            },
            "right_status_panel": {
                "x": right_status_rect.x, "y": right_status_rect.y, 
                "width": right_status_rect.width, "height": right_status_rect.height
            },
            "room_info_panel": {
                "x": room_panel_rect.x, "y": room_panel_rect.y, 
                "width": room_panel_rect.width, "height": room_panel_rect.height
            },
            "text_area": {
                "x": text_area_rect.x, "y": text_area_rect.y, 
                "width": text_area_rect.width, "height": text_area_height
            }
        }

    def draw(self):
        self.calculate_layout()
        self._static_hotspots = []
        self.screen.fill(BG_COLOR)
        
        self.cursor_timer += self.game.clock.get_time()
        if self.cursor_timer >= 500:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0

        # Mapping game states to render functions
        # FIX: Ensure all values are callables that accept (self) as an argument
        # 'screens' module functions take 'renderer' as arg, so we pass 'self'
        # '_draw_playing_screen' is a bound method, so we wrap it in lambda to accept the extra arg or just use it directly?
        # The simplest fix for the traceback "takes 1 positional argument but 2 were given"
        # is to standardize the call.
        
        state_renderer_map = {
            "title_screen": screens.draw_title_screen,
            "load_game_menu": screens.draw_load_screen,
            "playing": lambda r: self._draw_playing_screen(), # Wrap bound method to ignore the 'r' argument
            "game_over": screens.draw_game_over_screen,
            "character_creation": screens.draw_character_creation_screen,
        }
        
        renderer_func = state_renderer_map.get(self.game.game_state)
        if renderer_func:
            renderer_func(self) # Pass 'self' as the renderer instance to external functions

        if self.game.debug_mode:
             debug_text = "DEBUG" + (" (Levels ON)" if DEBUG_SHOW_LEVEL else "")
             debug_surface = self.font.render(debug_text, True, DEBUG_COLOR)
             self.screen.blit(debug_surface, (self.layout["screen_width"] - debug_surface.get_width() - 10, 5))

        pygame.display.flip()

    def scroll(self, amount_pixels: int):
        content_height = self.total_rendered_height
        visible_height = self.layout.get("text_area", {}).get("height", SCREEN_HEIGHT)
        max_scroll = max(0, content_height - visible_height)
        self.scroll_offset = max(0, min(max_scroll, self.scroll_offset + amount_pixels))

    # --- Internal Draw Methods ---

    def _draw_playing_screen(self):
        # 1. Layout & Bounds
        self.calculate_layout()
        
        left_rect = None
        right_rect = None
        if "left_status_panel" in self.layout:
            d = self.layout["left_status_panel"]
            left_rect = pygame.Rect(d["x"], d["y"], d["width"], d["height"])
        if "right_status_panel" in self.layout:
            d = self.layout["right_status_panel"]
            right_rect = pygame.Rect(d["x"], d["y"], d["width"], d["height"])
        
        if left_rect and right_rect:
            self.game.ui_manager.update_bounds(left_rect, right_rect)

        # 2. Static Elements
        panels.draw_time_bar(self, self.game.time_manager.time_data)
        panels.draw_room_info_panel(self, self.game.world)
        
        self._draw_text_area()
        self._draw_input_area()
        
        # 3. Draggable Panels
        resolved_player = self.game.world.resolve_reference_player() if self.game.world else None
        if self.game.world and resolved_player:
            context = {
                "player": resolved_player,
                "world": self.game.world,
                "game": self.game
            }
            self.game.ui_manager.update_and_draw(self.screen, context)
            # Sync Hotspots
            self._static_hotspots = self.game.ui_manager.active_hotspots

        # 4. Inventory Overlay
        if self.game.show_inventory:
            text_layout = self.layout.get("text_area")
            input_layout = self.layout.get("input_area")
            
            if text_layout and input_layout:
                overlay_rect = pygame.Rect(
                    text_layout["x"],
                    text_layout["y"],
                    text_layout["width"],
                    text_layout["height"] + input_layout["height"] + 10
                )
                self.inventory_menu.render(self.screen, overlay_rect)
                for r, cmd in self.inventory_menu.active_hotspots:
                    self._static_hotspots.append(ClickableZone(r, cmd))

        # 5. Draw Visual Juice (Floating Text)
        # We need dt for smooth animation, but update() handles logic. 
        # Ideally, we pass dt to draw, but for now we calculate simplistic frame time or rely on fixed step.
        # Let's grab the last clock tick from game if possible, or just use a small constant for visual smoothness.
        dt = 0.033 # Approx 30 FPS
        
        active_texts = []
        for ft in self.floating_texts:
            if ft.update(dt):
                ft.draw(self.screen, self.title_font) # Use larger font for impact
                active_texts.append(ft)
        self.floating_texts = active_texts

    def _draw_text_area(self):
        """
        Optimized text area drawing using a cached surface.
        """
        text_area_layout = self.layout.get("text_area")
        if not text_area_layout: return
        
        visible_rect = pygame.Rect(
            text_area_layout["x"], 
            text_area_layout["y"], 
            text_area_layout["width"], 
            text_area_layout["height"]
        )
        
        pygame.draw.rect(self.screen, BG_COLOR, visible_rect)

        if not self.text_buffer:
            return

        if self._text_dirty or self._cached_text_surface is None:
            self.text_formatter.update_screen_width(visible_rect.width)
            
            min_buffer_height = visible_rect.height + self.text_formatter.line_height_with_text * 5
            estimated_lines = sum(entry.count('\n') + 3 for entry in self.text_buffer)
            buffer_surface_height = max(min_buffer_height, estimated_lines * self.text_formatter.line_height_with_text)
            
            self._cached_text_surface = pygame.Surface((visible_rect.width, buffer_surface_height), pygame.SRCALPHA)
            self._cached_text_surface.fill((0, 0, 0, 0)) 
            
            raw_content_height = self.text_formatter.render(
                self._cached_text_surface, 
                "\n\n".join(self.text_buffer), 
                (0, 0)
            )
            
            # CAPTURE HOTSPOTS
            self._text_area_hotspots = self.text_formatter.last_hotspots[:]
            
            self.total_rendered_height = max(visible_rect.height, raw_content_height + (self.text_formatter.line_spacing // 2))
            self._text_dirty = False
            
            max_scroll_offset = max(0, self.total_rendered_height - visible_rect.height)
            if self.scroll_offset > max_scroll_offset - 100: 
                self.scroll_offset = max_scroll_offset 
        
        content_height = self.total_rendered_height
        max_scroll_offset = max(0, content_height - visible_rect.height)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll_offset))
        
        source_y = max(0, content_height - visible_rect.height - self.scroll_offset)
        blit_height = max(0, min(visible_rect.height, content_height - source_y))
        
        if blit_height > 0 and self._cached_text_surface:
            self.screen.blit(
                self._cached_text_surface, 
                (visible_rect.x, visible_rect.y), 
                pygame.Rect(0, source_y, visible_rect.width, blit_height)
            )
            
        self._draw_scroll_indicator(visible_rect)

    def _draw_input_area(self):
        layout = self.layout.get("input_area")
        if not layout: return

        rect = pygame.Rect(layout["x"], layout["y"], layout["width"], layout["height"])
        pygame.draw.rect(self.screen, INPUT_BG_COLOR, rect)
        
        input_display = "> " + self.game.input_handler.input_text
        if self.cursor_visible: input_display += "|"
        
        input_surface = self.font.render(input_display, True, TEXT_COLOR)
        
        input_y_pos = rect.y + (rect.height - input_surface.get_height()) // 2
        input_x_pos = rect.x + self.text_formatter.margin
        
        self.screen.blit(input_surface, (input_x_pos, input_y_pos))

    def _draw_scroll_indicator(self, text_area_rect: pygame.Rect):
        if not hasattr(self, 'total_rendered_height') or self.total_rendered_height <= text_area_rect.height: return
        arrow_x = text_area_rect.right - 15; arrow_width = 8; arrow_height = 8; arrow_color = (180, 180, 180)
        max_scroll = max(0, self.total_rendered_height - text_area_rect.height)
        if self.scroll_offset < max_scroll:
            pygame.draw.polygon(self.screen, arrow_color, [(arrow_x, text_area_rect.top + 5), (arrow_x - arrow_width, text_area_rect.top + 5 + arrow_height), (arrow_x + arrow_width, text_area_rect.top + 5 + arrow_height)])
        if self.scroll_offset > 0:
            pygame.draw.polygon(self.screen, arrow_color, [(arrow_x, text_area_rect.bottom - 5), (arrow_x - arrow_width, text_area_rect.bottom - 5 - arrow_height), (arrow_x + arrow_width, text_area_rect.bottom - 5 - arrow_height)])

    def _draw_centered_text(self, text, font, color, y_offset=0):
        # Kept for internal use if needed, though screens.py handles most now
        surface = font.render(text, True, color)
        rect = surface.get_rect(center=(self.layout["screen_width"] // 2, self.layout["screen_height"] // 2 + y_offset))
        self.screen.blit(surface, rect)

    def add_message(self, message: str):
        clean_message = self._sanitize_text(message)
        self.text_buffer.append(clean_message)
        if len(self.text_buffer) > MAX_BUFFER_LINES:
            self.text_buffer.pop(0)
        self._text_dirty = True

    def _sanitize_text(self, text: str) -> str:
        if not text: return ""
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = ''.join(ch if ch == '\n' or ord(ch) >= 32 else ' ' for ch in text)
        while '\n\n\n' in text: text = text.replace('\n\n\n', '\n\n')
        return text
