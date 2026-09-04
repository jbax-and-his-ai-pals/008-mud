# engine/ui/panels/targets.py
import pygame
from typing import TYPE_CHECKING
from engine.config import (
    STATUS_PANEL_PADDING, FORMAT_TITLE, FORMAT_RESET, FORMAT_GRAY, DEFAULT_COLORS
)
from engine.utils.text_formatter import format_target_name

if TYPE_CHECKING:
    from engine.ui.renderer import Renderer
    from engine.player import Player
    from engine.world.world import World

def draw_right_status_panel(renderer: 'Renderer', player: 'Player', world: 'World'):
    panel_layout = renderer.layout.get("right_status_panel")
    if not panel_layout: return
    panel_rect = pygame.Rect(panel_layout["x"], panel_layout["y"], panel_layout["width"], panel_layout["height"])
    pygame.draw.rect(renderer.screen, (20, 20, 20), panel_rect)
    pygame.draw.rect(renderer.screen, (80, 80, 80), panel_rect, 1)
    
    padding = STATUS_PANEL_PADDING
    line_height = renderer.text_formatter.line_height_with_text
    current_y = panel_rect.y + padding
    max_y = panel_rect.bottom - padding
    title_color = DEFAULT_COLORS.get(FORMAT_TITLE, (255, 255, 0))
    gray_color = DEFAULT_COLORS.get(FORMAT_GRAY, (128, 128, 128))

    all_npcs_in_room = world.get_current_room_npcs(player)

    original_width = renderer.text_formatter.screen_width
    renderer.text_formatter.update_screen_width(panel_rect.width)

    try:
        # --- PEOPLE (Friendlies/Neutrals) ---
        if current_y + line_height <= max_y:
            renderer.screen.blit(renderer.font.render("PEOPLE", True, title_color), (panel_rect.x + padding, current_y))
            current_y += line_height
        
        friendly_targets = [npc for npc in all_npcs_in_room if npc.is_alive and npc.faction in ["friendly", "neutral"]]
        if friendly_targets:
            for target in friendly_targets:
                if current_y >= max_y: break
                
                raw_name = format_target_name(player, target)
                clickable_name = f"[[CMD:look {target.name}]]- {raw_name}[[/CMD]]"
                
                current_y = renderer.text_formatter.render(renderer.screen, clickable_name, (panel_rect.x + padding + 5, current_y), max_height=(max_y - current_y))
                # Capture Hotspots immediately
                renderer._static_hotspots.extend(renderer.text_formatter.last_hotspots)
        else:
            if current_y + line_height <= max_y:
                renderer.screen.blit(renderer.font.render("- (None)", True, gray_color), (panel_rect.x + padding + 5, current_y))
                current_y += line_height
        current_y += line_height // 2

        # --- HOSTILES ---
        if current_y + line_height <= max_y:
            renderer.screen.blit(renderer.font.render("HOSTILES", True, title_color), (panel_rect.x + padding, current_y))
            current_y += line_height
        
        hostile_targets = [npc for npc in all_npcs_in_room if npc.is_alive and npc.faction == "hostile"]
        if hostile_targets:
            for target in hostile_targets:
                if current_y >= max_y: break
                
                raw_name = format_target_name(player, target)
                clickable_name = f"[[CMD:look {target.name}]]- {raw_name}[[/CMD]]"
                
                current_y = renderer.text_formatter.render(renderer.screen, clickable_name, (panel_rect.x + padding + 5, current_y), max_height=(max_y - current_y))
                # Capture Hotspots immediately
                renderer._static_hotspots.extend(renderer.text_formatter.last_hotspots)
        else:
            if current_y + line_height <= max_y:
                renderer.screen.blit(renderer.font.render("- (None)", True, gray_color), (panel_rect.x + padding + 5, current_y))
                current_y += line_height
    
    finally:
        renderer.text_formatter.update_screen_width(original_width)
