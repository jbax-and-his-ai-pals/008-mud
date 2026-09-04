# engine/ui/panels/status.py
import math
import time
import pygame
from typing import TYPE_CHECKING, Optional
from engine.config import (
    STATUS_PANEL_PADDING, FORMAT_TITLE, FORMAT_RESET, TEXT_COLOR,
    FORMAT_YELLOW, FORMAT_SUCCESS, FORMAT_ERROR, FORMAT_CYAN, FORMAT_ORANGE, FORMAT_GRAY,
    PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD, PLAYER_STATUS_HEALTH_LOW_THRESHOLD,
    VALID_DAMAGE_TYPES, EQUIPMENT_SLOTS, DEFAULT_COLORS
)
from engine.items.item import Item
from engine.magic.spell_registry import get_spell

if TYPE_CHECKING:
    from engine.ui.renderer import Renderer
    from engine.player import Player

def draw_left_status_panel(renderer: 'Renderer', player: 'Player'):
    panel_layout = renderer.layout.get("left_status_panel")
    if not panel_layout: return
    panel_rect = pygame.Rect(panel_layout["x"], panel_layout["y"], panel_layout["width"], panel_layout["height"])
    pygame.draw.rect(renderer.screen, (20, 20, 20), panel_rect)
    pygame.draw.rect(renderer.screen, (80, 80, 80), panel_rect, 1)

    padding = STATUS_PANEL_PADDING
    line_height = renderer.text_formatter.line_height_with_text
    current_y = panel_rect.y + padding
    max_y = panel_rect.bottom - padding

    original_width = renderer.text_formatter.screen_width 
    renderer.text_formatter.update_screen_width(panel_rect.width)

    try:
        current_y = renderer.text_formatter.render(renderer.screen, f"{FORMAT_TITLE}{player.name}{FORMAT_RESET}", (panel_rect.x + padding, current_y), max_height=(max_y - current_y))
        if current_y < max_y: renderer.screen.blit(renderer.font.render(f"Level: {player.runtime_state.progression.level}", True, TEXT_COLOR), (panel_rect.x + padding, current_y)); current_y += line_height
        if current_y < max_y: current_y = renderer.text_formatter.render(renderer.screen, f"Gold: {FORMAT_YELLOW}{player.runtime_state.gold}{FORMAT_RESET}", (panel_rect.x + padding, current_y), max_height=(max_y - current_y))
        current_y += line_height // 2

        bar_height = 10
        bar_x = panel_rect.x + padding
        bar_label_width = renderer.font.size("HP: 9999/9999")[0] + 5
        max_bar_width = max(20, panel_layout["width"] - (padding * 2) - bar_label_width)
        
        # --- HP BAR ---
        if current_y + bar_height <= max_y:
            hp_text = f"HP: {int(player.health)}/{int(player.max_health)}"; hp_percent = player.health / player.max_health if player.max_health > 0 else 0
            hp_color = DEFAULT_COLORS[FORMAT_SUCCESS]
            if hp_percent <= PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD / 100: hp_color = DEFAULT_COLORS[FORMAT_ERROR]
            elif hp_percent <= PLAYER_STATUS_HEALTH_LOW_THRESHOLD / 100: hp_color = DEFAULT_COLORS[FORMAT_YELLOW]
            pygame.draw.rect(renderer.screen, (80, 0, 0), (bar_x, current_y, max_bar_width, bar_height))
            pygame.draw.rect(renderer.screen, hp_color, (bar_x, current_y, int(max_bar_width * hp_percent), bar_height))
            hp_surface = renderer.font.render(hp_text, True, hp_color)
            renderer.screen.blit(hp_surface, (bar_x + max_bar_width + padding, current_y + (bar_height // 2) - (hp_surface.get_height() // 2)))
            current_y += bar_height + padding
        
        # --- MP BAR ---
        if current_y + bar_height <= max_y:
            mp_text = f"MP: {int(player.runtime_state.magic.mana)}/{int(player.runtime_state.magic.max_mana)}"; mp_percent = player.runtime_state.magic.mana / player.runtime_state.magic.max_mana if player.runtime_state.magic.max_mana > 0 else 0
            mp_color = DEFAULT_COLORS[FORMAT_CYAN]
            pygame.draw.rect(renderer.screen, (0, 0, 80), (bar_x, current_y, max_bar_width, bar_height))
            pygame.draw.rect(renderer.screen, mp_color, (bar_x, current_y, int(max_bar_width * mp_percent), bar_height))
            mp_surface = renderer.font.render(mp_text, True, mp_color)
            renderer.screen.blit(mp_surface, (bar_x + max_bar_width + padding, current_y + (bar_height // 2) - (mp_surface.get_height() // 2)))
            current_y += bar_height + padding
        
        # --- XP BAR ---
        if current_y + bar_height <= max_y:
            xp_text = f"XP: {int(player.runtime_state.progression.experience)}/{int(player.runtime_state.progression.experience_to_level)}"; xp_percent = player.runtime_state.progression.experience / player.runtime_state.progression.experience_to_level if player.runtime_state.progression.experience_to_level > 0 else 0
            xp_color = DEFAULT_COLORS[FORMAT_ORANGE]
            pygame.draw.rect(renderer.screen, (80, 50, 0), (bar_x, current_y, max_bar_width, bar_height))
            pygame.draw.rect(renderer.screen, xp_color, (bar_x, current_y, int(max_bar_width * xp_percent), bar_height))
            xp_surface = renderer.font.render(xp_text, True, xp_color)
            renderer.screen.blit(xp_surface, (bar_x + max_bar_width + padding, current_y + (bar_height // 2) - (xp_surface.get_height() // 2)))
            current_y += bar_height + padding
        
        title_color = DEFAULT_COLORS.get(FORMAT_TITLE, (255, 255, 0))
        
        # --- STATS ---
        if current_y + line_height <= max_y: 
            renderer.screen.blit(renderer.font.render("STATS", True, title_color), (panel_rect.x + padding, current_y))
            current_y += line_height
        
        stats_to_show = {"strength": "STR", "dexterity": "DEX", "constitution": "CON", "agility": "AGI", "intelligence": "INT", "wisdom": "WIS", "spell_power": "SP", "magic_resist": "MR"}
        stats_per_col = math.ceil(len(stats_to_show) / 2)
        col1_x = panel_rect.x + padding + 5
        col2_x = col1_x + (panel_layout["width"] - padding * 2 - 10) // 2
        col1_y, col2_y = current_y, current_y

        for i, (stat_key, stat_abbr) in enumerate(stats_to_show.items()):
            if max(col1_y, col2_y) + line_height > max_y:
                break
            base_stat = player.stats.get(stat_key, 0)
            effective_stat = player.get_effective_stat(stat_key)
            color = FORMAT_RESET
            if effective_stat > base_stat: color = FORMAT_SUCCESS
            elif effective_stat < base_stat: color = FORMAT_ERROR
            stat_text = f"{stat_abbr}: {color}{effective_stat}{FORMAT_RESET}"
            if i < stats_per_col:
                col1_y = renderer.text_formatter.render(renderer.screen, stat_text, (col1_x, col1_y), max_height=(max_y - col1_y))
            else:
                col2_y = renderer.text_formatter.render(renderer.screen, stat_text, (col2_x, col2_y), max_height=(max_y - col2_y))
        current_y = max(col1_y, col2_y) + line_height // 2

        # --- RESISTANCES ---
        resistance_parts = []
        for dmg_type in VALID_DAMAGE_TYPES:
            res_value = player.get_resistance(dmg_type)
            if res_value != 0:
                color = FORMAT_SUCCESS if res_value > 0 else FORMAT_ERROR
                resistance_parts.append(f"{dmg_type.capitalize()} {color}{res_value:+}%{FORMAT_RESET}")
        if resistance_parts and current_y + line_height <= max_y:
            renderer.screen.blit(renderer.font.render("RESISTANCES", True, title_color), (panel_rect.x + padding, current_y))
            current_y += line_height
            resists_per_col = math.ceil(len(resistance_parts) / 2)
            col1_y_res, col2_y_res = current_y, current_y
            for i, res_text in enumerate(resistance_parts):
                if max(col1_y_res, col2_y_res) + line_height > max_y: break
                if i < resists_per_col:
                    col1_y_res = renderer.text_formatter.render(renderer.screen, res_text, (col1_x, col1_y_res), max_height=(max_y - col1_y_res))
                else:
                    col2_y_res = renderer.text_formatter.render(renderer.screen, res_text, (col2_x, col2_y_res), max_height=(max_y - col2_y_res))
            current_y = max(col1_y_res, col2_y_res) + line_height // 2

        # --- EQUIPMENT ---
        if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("EQUIPPED", True, title_color), (panel_rect.x + padding, current_y)); current_y += line_height
        def format_equip_slot(slot_abbr: str, item: Optional[Item]) -> str:
            if not item: return f"{slot_abbr}: {FORMAT_GRAY}(Empty){FORMAT_RESET}"
            durability_str = ""
            max_durability = item.get_property("max_durability", 0); current_durability = item.get_property("durability", max_durability)
            if max_durability > 0:
                ratio = current_durability / max_durability if max_durability else 0; dura_color = FORMAT_SUCCESS
                if ratio <= 0.1: dura_color = FORMAT_ERROR
                elif ratio <= 0.3: dura_color = FORMAT_YELLOW
                durability_str = f" [{dura_color}{int(current_durability)}/{int(max_durability)}{FORMAT_RESET}]"
            return f"{slot_abbr}: {item.name}{durability_str}"
        slot_abbrs = {"main_hand": "MH", "off_hand": "OH", "head": "Hd", "body": "Bd", "hands": "Hn", "feet": "Ft", "neck": "Nk"}
        for slot_key in EQUIPMENT_SLOTS:
            if current_y >= max_y: break
            current_y = renderer.text_formatter.render(renderer.screen, f"- {format_equip_slot(slot_abbrs[slot_key], player.equipment.get(slot_key))}", (panel_rect.x + padding + 5, current_y), max_height=(max_y - current_y))
        current_y += line_height // 2

        # --- SPELLS ---
        gray_color = DEFAULT_COLORS.get(FORMAT_GRAY, (128, 128, 128))
        error_color = DEFAULT_COLORS.get(FORMAT_ERROR, (255,0,0))
        text_color = DEFAULT_COLORS.get(FORMAT_RESET, TEXT_COLOR)
        if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("SPELLS", True, title_color), (panel_rect.x + padding, current_y)); current_y += line_height
        if player.runtime_state.magic.known_spells:
            current_time = time.time()
            for spell_id in sorted(list(player.runtime_state.magic.known_spells), key=lambda sid: getattr(get_spell(sid), 'name', sid)):
                if current_y + line_height > max_y: break
                spell = get_spell(spell_id)
                if spell:
                    cooldown_end = player.runtime_state.magic.cooldowns.get(spell_id, 0)
                    cd_status = f" (CD {max(0, cooldown_end - current_time):.1f}s)" if current_time < cooldown_end else ""
                    spell_text = f"- {spell.name} ({spell.mana_cost} MP)"
                    renderer.screen.blit(renderer.font.render(spell_text, True, text_color), (panel_rect.x + padding + 5, current_y))
                    if cd_status:
                        renderer.screen.blit(renderer.font.render(cd_status, True, error_color), (panel_rect.x + padding + 5 + renderer.font.size(spell_text)[0], current_y))
                    current_y += line_height
        else:
            if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("(None known)", True, gray_color), (panel_rect.x + padding + 5, current_y)); current_y += line_height
        current_y += line_height // 2

        # --- SKILLS ---
        if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("SKILLS", True, title_color), (panel_rect.x + padding, current_y)); current_y += line_height
        if player.runtime_state.progression.skills:
            for skill_name, level in sorted(player.runtime_state.progression.skills.items()):
                if current_y + line_height > max_y: break
                renderer.screen.blit(renderer.font.render(f"- {skill_name.capitalize()}: {level}", True, text_color), (panel_rect.x + padding + 5, current_y)); current_y += line_height
        else:
            if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("(None known)", True, gray_color), (panel_rect.x + padding + 5, current_y)); current_y += line_height
        current_y += line_height // 2
        
        # --- EFFECTS ---
        if current_y + line_height <= max_y: renderer.screen.blit(renderer.font.render("EFFECTS", True, title_color), (panel_rect.x + padding, current_y)); current_y += line_height
        if player.active_effects:
            for effect in sorted(player.active_effects, key=lambda e: e.get("name", "zzz")):
                if current_y >= max_y: break
                name = effect.get('name', 'Unknown Effect'); duration = effect.get('duration_remaining', 0)
                duration_str = f"{duration / 60:.1f}m" if duration > 60 else f"{duration:.1f}s"
                details = ""
                if effect.get("type") == "dot":
                    details = f" ({FORMAT_ERROR}{effect.get('damage_per_tick', 0)}/tick{FORMAT_RESET})"
                elif effect.get("type") == "hot":
                    details = f" ({FORMAT_SUCCESS}+{effect.get('heal_per_tick', 0)}/tick{FORMAT_RESET})"
                current_y = renderer.text_formatter.render(renderer.screen, f"- {name}{details} ({duration_str})", (panel_rect.x + padding + 5, current_y), max_height=(max_y - current_y))
        else:
            if current_y + line_height <= max_y:
                renderer.screen.blit(renderer.font.render("- (None)", True, gray_color), (panel_rect.x + padding + 5, current_y)); current_y += line_height

    finally:
        renderer.text_formatter.update_screen_width(original_width)
