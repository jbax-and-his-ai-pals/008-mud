# engine/ui/ui_manager.py
import pygame
from typing import List, Any, Optional, Tuple, Dict, Callable
from engine.ui.ui_element import UIPanel, HEADER_HEIGHT
from engine.ui.context_menu import ContextMenu
from engine.utils.text_formatter import ClickableZone
from engine.items.item import Item
from engine.magic.spell import Spell
from engine.npcs.npc import NPC

GAP = 10
PREVIEW_BORDER_COLOR = (100, 200, 255)
PREVIEW_FILL_COLOR = (100, 200, 255, 40)
SHADOW_COLOR = (0, 0, 0, 128)
SHADOW_OFFSET = (8, 8)

class UIManager:
    def __init__(self):
        self.left_dock: List[UIPanel] = []
        self.right_dock: List[UIPanel] = []
        self.left_bounds = pygame.Rect(0, 0, 100, 100)
        self.right_bounds = pygame.Rect(0, 0, 100, 100)
        
        self.dragging_panel: Optional[UIPanel] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_pos: Tuple[int, int] = (0, 0)

        self.active_hotspots: List[ClickableZone] = []
        self.all_panels_registry: Dict[str, UIPanel] = {}
        
        # Context Menu
        self.context_menu: Optional[ContextMenu] = None
        self.on_command_callback: Optional[Callable[[str], None]] = None

    def register_panel(self, panel: UIPanel):
        self.all_panels_registry[panel.panel_id] = panel

    def add_panel_to_dock(self, panel_id: str, side: str = "left") -> bool:
        panel = self.all_panels_registry.get(panel_id)
        if not panel: return False
        if panel in self.left_dock or panel in self.right_dock: return False
        if side == "left": self.left_dock.append(panel)
        else: self.right_dock.append(panel)
        return True

    def remove_panel(self, panel_id: str) -> bool:
        panel = self.all_panels_registry.get(panel_id)
        if not panel: return False
        if panel in self.left_dock: self.left_dock.remove(panel); return True
        if panel in self.right_dock: self.right_dock.remove(panel); return True
        return False

    def update_bounds(self, left_rect: pygame.Rect, right_rect: pygame.Rect):
        self.left_bounds = left_rect
        self.right_bounds = right_rect

    def open_context_menu(self, data: Any, pos: Tuple[int, int]):
        """Generates options based on data type and opens menu."""
        options = []
        
        if isinstance(data, Item):
            options.append(("Examine", f"look {data.name}"))
            
            # Item Type Specifics
            if data.__class__.__name__ == "Weapon" or data.__class__.__name__ == "Armor":
                # Determine if equipped (Simple check: command context usually implies intent)
                # We don't have player context here easily, so we offer generic commands
                # The game logic handles validity.
                options.append(("Equip", f"equip {data.name}"))
                options.append(("Unequip", f"unequip {data.name}"))
            elif data.__class__.__name__ == "Consumable" or data.__class__.__name__ == "Key":
                options.append(("Use", f"use {data.name}"))
            elif data.__class__.__name__ == "Container":
                options.append(("Open", f"open {data.name}"))
                options.append(("Close", f"close {data.name}"))
                options.append(("Look In", f"look in {data.name}"))
                
            options.append(("Drop", f"drop {data.name}"))
        
        elif isinstance(data, NPC):
            options.append(("Look", f"look {data.name}"))
            options.append(("Talk", f"talk {data.name}"))
            if data.faction == "hostile":
                options.append(("Attack", f"attack {data.name}"))
            elif data.properties.get("is_vendor"):
                options.append(("Trade", f"trade {data.name}"))
        
        elif isinstance(data, Spell):
            options.append(("Cast", f"cast {data.name}"))
            
        if options:
            options.append(("Cancel", ""))
            self.context_menu = ContextMenu(pos[0], pos[1], options)

    def handle_event(self, event: pygame.event.Event) -> bool:
        # 1. Context Menu Priority
        if self.context_menu:
            cmd = self.context_menu.handle_event(event)
            if cmd:
                self.context_menu = None # Close menu
                if cmd != "CLOSE_MENU" and cmd != "" and self.on_command_callback:
                    self.on_command_callback(cmd)
                return True # Consumed
            # If clicked outside (returns CLOSE_MENU), we consumed the click to close it
        
        # 2. Dragging Logic
        if event.type == pygame.MOUSEBUTTONDOWN:
            all_panels = self.left_dock + self.right_dock
            for panel in all_panels:
                header_rect = pygame.Rect(panel.rect.x, panel.rect.y, panel.rect.width, HEADER_HEIGHT)
                if header_rect.collidepoint(event.pos):
                    if event.button == 3: # Right Click Collapse
                        panel.is_collapsed = not panel.is_collapsed
                        return True
                    if event.button == 1: # Left Click Drag
                        self.dragging_panel = panel
                        self.drag_offset = (event.pos[0] - panel.rect.x, event.pos[1] - panel.rect.y)
                        self.drag_pos = event.pos
                        if panel in self.left_dock: self.left_dock.remove(panel)
                        if panel in self.right_dock: self.right_dock.remove(panel)
                        return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.dragging_panel:
                self._drop_panel()
                self.dragging_panel = None
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_panel:
                self.drag_pos = event.pos
                return True

        return False

    # ... (drop info, drop panel methods remain the same) ...
    def _get_drop_info(self) -> Tuple[List[UIPanel], int, pygame.Rect]:
        mx, my = self.drag_pos
        dist_to_left = abs(mx - self.left_bounds.centerx)
        dist_to_right = abs(mx - self.right_bounds.centerx)
        
        target_list = self.left_dock if dist_to_left < dist_to_right else self.right_dock
        target_rect = self.left_bounds if dist_to_left < dist_to_right else self.right_bounds
        
        panel_y = my - self.drag_offset[1]
        insert_index = len(target_list)
        current_y = target_rect.y
        for i, existing_panel in enumerate(target_list):
            h = existing_panel.current_height
            mid_point = current_y + (h // 2)
            if panel_y < mid_point:
                insert_index = i
                break
            current_y += h + GAP
        return target_list, insert_index, target_rect

    def _drop_panel(self):
        if not self.dragging_panel: return
        target_list, insert_index, _ = self._get_drop_info()
        target_list.insert(insert_index, self.dragging_panel)

    def update_and_draw(self, screen: pygame.Surface, context_data: Any):
        self.active_hotspots = []

        target_dock_list: Optional[List[UIPanel]] = None
        insert_index: int = -1
        target_dock_bounds: Optional[pygame.Rect] = None
        
        if self.dragging_panel:
            target_dock_list, insert_index, target_dock_bounds = self._get_drop_info()

        def draw_dock(dock_list: List[UIPanel], bounds: pygame.Rect):
            y = bounds.y
            width = bounds.width
            
            for i, panel in enumerate(dock_list):
                if self.dragging_panel and dock_list is target_dock_list and i == insert_index:
                     if self.dragging_panel: 
                        y += self.dragging_panel.current_height + GAP

                panel.resize(width, panel.target_height)
                panel.update(context_data)
                panel.draw(screen, bounds.x, y)
                
                if not panel.is_collapsed:
                    content_abs_x = bounds.x
                    content_abs_y = y + HEADER_HEIGHT
                    for zone in panel.hotspots:
                        abs_rect = pygame.Rect(
                            content_abs_x + zone.rect.x,
                            content_abs_y + zone.rect.y,
                            zone.rect.width, zone.rect.height
                        )
                        # Pass data through
                        self.active_hotspots.append(ClickableZone(abs_rect, zone.command, zone.data))

                y += panel.current_height + GAP

        draw_dock(self.left_dock, self.left_bounds)
        draw_dock(self.right_dock, self.right_bounds)
        
        if self.dragging_panel and target_dock_bounds and target_dock_list is not None:
            draw_x = self.drag_pos[0] - self.drag_offset[0]
            draw_y = self.drag_pos[1] - self.drag_offset[1]
            
            preview_y = target_dock_bounds.y
            for i in range(insert_index):
                preview_y += target_dock_list[i].current_height + GAP
            
            drag_current_h = self.dragging_panel.current_height
            preview_rect = pygame.Rect(target_dock_bounds.x, preview_y, target_dock_bounds.width, drag_current_h)
            
            preview_surf = pygame.Surface((preview_rect.width, preview_rect.height), pygame.SRCALPHA)
            preview_surf.fill(PREVIEW_FILL_COLOR)
            screen.blit(preview_surf, (preview_rect.x, preview_rect.y))
            pygame.draw.rect(screen, PREVIEW_BORDER_COLOR, preview_rect, 2)
            
            self.dragging_panel.resize(target_dock_bounds.width, self.dragging_panel.target_height)
            self.dragging_panel.update(context_data)
            
            shadow_rect = pygame.Rect(draw_x + SHADOW_OFFSET[0], draw_y + SHADOW_OFFSET[1], self.dragging_panel.rect.width, drag_current_h)
            shadow_surf = pygame.Surface((shadow_rect.width, shadow_rect.height), pygame.SRCALPHA)
            shadow_surf.fill(SHADOW_COLOR)
            screen.blit(shadow_surf, (shadow_rect.x, shadow_rect.y))

            self.dragging_panel.draw(screen, draw_x, draw_y)
            
        # Draw Context Menu LAST
        if self.context_menu:
            self.context_menu.draw(screen)