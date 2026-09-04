# engine/ui/screens.py
import pygame
from typing import TYPE_CHECKING
from engine.config import *
from engine.magic.spell_registry import get_spell

if TYPE_CHECKING:
    from engine.ui.renderer import Renderer

def draw_title_screen(renderer: 'Renderer'):
    renderer._draw_centered_text("Pygame MUD", renderer.title_font, (200, 200, 50), y_offset=-100)
    for i, option in enumerate(renderer.game.title_options):
        font = renderer.selected_font if i == renderer.game.selected_title_option else renderer.font
        color = (255, 255, 100) if i == renderer.game.selected_title_option else TEXT_COLOR
        prefix = "> " if i == renderer.game.selected_title_option else "  "
        renderer._draw_centered_text(f"{prefix}{option}", font, color, y_offset=-20 + i * 40)

def draw_load_screen(renderer: 'Renderer'):
    renderer._draw_centered_text("Load Game", renderer.title_font, (200, 200, 50), y_offset=-150)
    option_start_y = -100; option_spacing = 30; max_display = 10
    if not renderer.game.available_saves:
        renderer._draw_centered_text("No save files found.", renderer.font, (180, 180, 180))
    for i in range(max_display):
        display_index = i
        if display_index >= len(renderer.game.available_saves): break
        save_name = renderer.game.available_saves[display_index]
        is_selected = (display_index == renderer.game.selected_load_option)
        font = renderer.selected_font if is_selected else renderer.font
        color = (255, 255, 100) if is_selected else TEXT_COLOR
        prefix = "> " if is_selected else "  "
        renderer._draw_centered_text(f"{prefix}{save_name}", font, color, y_offset=option_start_y + i * option_spacing)
    
    back_selected = (renderer.game.selected_load_option == len(renderer.game.available_saves))
    back_font = renderer.selected_font if back_selected else renderer.font
    back_color = (255, 255, 100) if back_selected else TEXT_COLOR
    back_prefix = "> " if back_selected else "  "
    renderer._draw_centered_text(f"{back_prefix}[ Back ]", back_font, back_color, y_offset=option_start_y + max_display * option_spacing + 20)

def draw_character_creation_screen(renderer: 'Renderer'):
    sw, sh = renderer.layout["screen_width"], renderer.layout["screen_height"]
    
    # Header
    renderer._draw_centered_text("Character Creation", renderer.title_font, (255, 215, 0), y_offset=-(sh//2) + 40)
    
    # Unified Colors
    active_color = (100, 255, 100)
    inactive_color = (100, 100, 100)
    bg_active = (60, 60, 70)
    text_white = (255, 255, 255)
    text_grey = (180, 180, 180)
    
    # Determine focus
    name_focused = (renderer.game.creation_active_field == "name_input")
    name_border = active_color if name_focused else inactive_color

    # --- SECTION 1: NAME INPUT (Top) ---
    name_box_width = 400
    name_box_rect = pygame.Rect((sw - name_box_width)//2, 100, name_box_width, 50)
    
    # Visual feedback for focus
    pygame.draw.rect(renderer.screen, bg_active, name_box_rect)
    pygame.draw.rect(renderer.screen, name_border, name_box_rect, 2)
    
    label_surf = renderer.font.render("Name:", True, (200, 200, 200))
    renderer.screen.blit(label_surf, (name_box_rect.x - label_surf.get_width() - 10, name_box_rect.y + 15))
    
    name_txt = renderer.game.creation_name_input
    if name_focused and renderer.cursor_visible: name_txt += "|"
    name_surf = renderer.font.render(name_txt, True, text_white)
    text_rect = name_surf.get_rect(center=name_box_rect.center)
    renderer.screen.blit(name_surf, text_rect)

    # --- SECTION 2 & 3: CLASS SELECTION ---
    
    # Pushed down to 220 to avoid overlap with name box border
    content_y = 220
    content_height = sh - content_y - 80
    
    # Class List Area
    list_width = 250
    list_x = (sw // 2) - list_width - 20
    
    # Details Area
    details_width = 400
    details_x = (sw // 2) + 20
    
    list_focused = (renderer.game.creation_active_field == "class_list")
    header_color = active_color if list_focused else inactive_color
    
    # Header for Class List
    renderer.screen.blit(renderer.selected_font.render("Select Class", True, header_color), (list_x, content_y - 30))
    
    # Draw Class List Items
    for i, class_id in enumerate(renderer.game.available_classes):
        is_selected = (i == renderer.game.selected_class_index)
        cls_def = renderer.game.class_definitions.get(class_id, {})
        name = cls_def.get("name", class_id.title())
        
        item_y = content_y + (i * 40)
        
        if is_selected:
            bg_rect = pygame.Rect(list_x - 10, item_y - 5, list_width + 20, 30)
            pygame.draw.rect(renderer.screen, (60, 60, 80), bg_rect)
            # Border depends on focus
            border_col = active_color if list_focused else (150, 150, 150)
            pygame.draw.rect(renderer.screen, border_col, bg_rect, 1)
            color = (255, 255, 100)
            prefix = "> "
            font = renderer.selected_font
        else:
            color = text_grey
            prefix = "  "
            font = renderer.font
            
        text_surf = font.render(f"{prefix}{name}", True, color)
        renderer.screen.blit(text_surf, (list_x, item_y))

    # Draw Details Box
    details_rect = pygame.Rect(details_x, content_y, details_width, content_height)
    pygame.draw.rect(renderer.screen, (30, 30, 35), details_rect)
    pygame.draw.rect(renderer.screen, (100, 100, 100), details_rect, 2)
    
    selected_id = renderer.game.available_classes[renderer.game.selected_class_index]
    data = renderer.game.class_definitions.get(selected_id, {})
    
    # Description
    desc_y = details_rect.y + 15
    desc = data.get("description", "No description available.")
    renderer.text_formatter.update_screen_width(details_width - 20)
    stats_header_y = renderer.text_formatter.render(renderer.screen, desc, (details_rect.x + 10, desc_y)) + 20
    
    # Stats
    stat_font = pygame.font.SysFont("arial", 14)
    renderer.screen.blit(renderer.title_font.render("Base Stats:", True, (220, 220, 220)), (details_rect.x + 10, stats_header_y))
    
    stats_y = stats_header_y + 30
    stats = data.get("stats", {})
    row, col = 0, 0
    for stat, val in stats.items():
        if stat in ["spell_power", "magic_resist"]: continue
        val_col = (150, 255, 150) if val > 10 else ((255, 150, 150) if val < 10 else text_grey)
        
        lbl = stat.title()[:3]
        txt_surf = stat_font.render(f"{lbl}: ", True, text_grey)
        val_surf = stat_font.render(str(val), True, val_col)
        
        x_pos = details_rect.x + 10 + col * 90
        y_pos = stats_y + row * 20
        renderer.screen.blit(txt_surf, (x_pos, y_pos))
        renderer.screen.blit(val_surf, (x_pos + txt_surf.get_width(), y_pos))
        
        col += 1
        if col > 2:
            col = 0; row += 1
    
    # Spells
    spells = data.get("spells", [])
    if spells:
        spells_header_y = stats_y + (row + 1) * 20 + 20
        renderer.screen.blit(renderer.title_font.render("Starting Abilities:", True, (220, 220, 220)), (details_rect.x + 10, spells_header_y))
        
        for i, spell_id in enumerate(spells):
            spell = get_spell(spell_id)
            spell_name = spell.name if spell else spell_id.replace('_', ' ').title()
            txt = f"- {spell_name}"
            renderer.screen.blit(stat_font.render(txt, True, (150, 255, 255)), (details_rect.x + 20, spells_header_y + 30 + i*20))

    # Instructions
    inst_y = sh - 40
    controls = "[TAB/CLICK] Switch Focus  [TYPE] Name  [ARROWS] Select Class  [ENTER] Start"
    inst_surf = renderer.font.render(controls, True, (100, 255, 100))
    inst_rect = inst_surf.get_rect(center=(sw//2, inst_y))
    renderer.screen.blit(inst_surf, inst_rect)

def draw_game_over_screen(renderer: 'Renderer'):
    renderer._draw_centered_text(GAME_OVER_MESSAGE_LINE1, renderer.title_font, DEFAULT_COLORS[FORMAT_ERROR], y_offset=-20)
    renderer._draw_centered_text(GAME_OVER_MESSAGE_LINE2, renderer.font, TEXT_COLOR, y_offset=20)
