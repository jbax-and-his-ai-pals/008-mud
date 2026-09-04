# engine/ui/panel_content.py
from typing import Any, List
import pygame
import math
from engine.config import *
from engine.utils.text_formatter import TextFormatter, ClickableZone
from engine.ui import minimap
from engine.ui.icons import get_item_icon, ICON_SIZE

# ... (get_font, _draw_clickable_text helpers unchanged) ...
_font_cache = {}
def get_font(size=16, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(FONT_FAMILY, size, bold=bold)
    return _font_cache[key]

def _draw_clickable_text(surface: pygame.Surface, font, text: str, x: int, y: int, color: tuple, 
                        command: str, hotspots: List[ClickableZone], data: Any = None):
    surf = font.render(text, True, color)
    surface.blit(surf, (x, y))
    if command:
        rect = pygame.Rect(x, y, surf.get_width(), surf.get_height())
        hotspots.append(ClickableZone(rect, command, data))
    return y + surf.get_height()

# ... (render_minimap_content unchanged) ...
def render_minimap_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    world = context.get("world")
    player = context.get("player")
    if not world: return
    rect = surface.get_rect()
    minimap.draw_minimap(surface, rect, world, player=player)

def render_stats_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return

    y = 5
    padding = 5
    width = surface.get_width()
    
    # --- NEW: Header with Name, Level, Class ---
    name_font = get_font(16, bold=True)
    info_font = get_font(14, bold=False)
    
    # Name (Gold/Title Color)
    name_surf = name_font.render(player.name, True, (255, 215, 0))
    surface.blit(name_surf, (padding, y))
    y += 18
    
    # Level 5 Warrior
    cls_name = player.runtime_state.progression.player_class
    info_txt = f"Level {player.runtime_state.progression.level} {cls_name}"
    info_surf = info_font.render(info_txt, True, (200, 200, 200))
    surface.blit(info_surf, (padding, y))
    y += 22 # Extra spacing before bars

    # --- Rest of Stats ---
    font = get_font(14)

    def draw_line(text, color=TEXT_COLOR):
        nonlocal y
        surf = font.render(text, True, color)
        surface.blit(surf, (padding, y))
        y += 16

    draw_line(f"Health: {int(player.health)}/{int(player.max_health)}", DEFAULT_COLORS[FORMAT_SUCCESS])
    draw_line(f"Mana:   {int(player.runtime_state.magic.mana)}/{int(player.runtime_state.magic.max_mana)}", DEFAULT_COLORS[FORMAT_CYAN])
    draw_line(f"XP:     {player.runtime_state.progression.experience}/{player.runtime_state.progression.experience_to_level}", DEFAULT_COLORS[FORMAT_ORANGE])
    y += 5
    
    stats = ["strength", "dexterity", "constitution", "agility", "intelligence", "wisdom"]
    col_width = width // 2
    
    start_y = y
    for i, stat in enumerate(stats):
        val = player.get_effective_stat(stat)
        abbr = stat[:3].upper()
        
        col = i % 2
        row = i // 2
        
        pos_x = padding + (col * col_width)
        pos_y = start_y + (row * 16)
        
        txt = f"{abbr}: {val}"
        surf = font.render(txt, True, TEXT_COLOR)
        surface.blit(surf, (pos_x, pos_y))
        
    y = start_y + (3 * 16) + 5
    draw_line(f"Gold: {player.runtime_state.gold}", DEFAULT_COLORS[FORMAT_YELLOW])

# ... (rest of file: render_skills_content, render_equipment_content, etc. unchanged) ...
def render_skills_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return
    font = get_font(14)
    y, padding = 5, 5
    if not player.runtime_state.progression.skills:
        surface.blit(font.render("(No skills)", True, (150, 150, 150)), (padding, y))
        return
    for skill, level in sorted(player.runtime_state.progression.skills.items()):
        surface.blit(font.render(f"{skill.replace('_', ' ').title()}: {level}", True, TEXT_COLOR), (padding, y))
        y += 18

def render_equipment_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return
    font = get_font(14)
    y, padding = 5, 5
    
    for slot in EQUIPMENT_SLOTS:
        item = player.equipment.get(slot)
        slot_name = slot.replace('_', ' ').title()
        
        if item:
            text = f"{slot_name}: {item.name}"
            _draw_clickable_text(surface, font, text, padding, y, TEXT_COLOR, f"look {item.name}", hotspots, data=item)
        else:
            text = f"{slot_name}: (Empty)"
            surface.blit(font.render(text, True, (100, 100, 100)), (padding, y))
        y += 18

def render_spells_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return
    font = get_font(14)
    y, padding = 5, 5
    if not player.runtime_state.magic.known_spells:
        surface.blit(font.render("(No spells)", True, (150, 150, 150)), (padding, y))
        return
    from engine.magic.spell_registry import get_spell
    import time
    current_time = time.time()
    for spell_id in sorted(player.runtime_state.magic.known_spells):
        spell = get_spell(spell_id)
        if not spell: continue
        color = TEXT_COLOR
        cd_end = player.runtime_state.magic.cooldowns.get(spell_id, 0)
        if current_time < cd_end:
            color = (150, 50, 50)
            text = f"{spell.name} ({cd_end - current_time:.1f}s)"
        else:
            text = f"{spell.name} ({spell.mana_cost} MP)"
        cmd = f"cast {spell.name}"
        _draw_clickable_text(surface, font, text, padding, y, color, cmd, hotspots, data=spell)
        y += 18

def render_inventory_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    game = context.get("game")
    if not player or not game: return
    
    mode = game.inventory_mode 
    font = get_font(14)
    y, x, padding = 5, 5, 5
    
    if mode == "text":
        for slot in player.inventory.slots:
            if not slot.item: continue
            item = slot.item
            name = f"{item.name} (x{slot.quantity})" if slot.quantity > 1 else item.name
            cmd = f"look {item.name}"
            _draw_clickable_text(surface, font, name, padding, y, TEXT_COLOR, cmd, hotspots, data=item)
            y += 18

    elif mode == "icon":
        col_w = ICON_SIZE + padding
        row_h = ICON_SIZE + padding
        cols = max(1, surface.get_width() // col_w)
        
        current_col = 0
        for slot in player.inventory.slots:
            r = pygame.Rect(x, y, ICON_SIZE, ICON_SIZE)
            pygame.draw.rect(surface, (40, 40, 50), r)
            pygame.draw.rect(surface, (80, 80, 90), r, 1)
            
            if slot.item:
                icon = get_item_icon(slot.item)
                surface.blit(icon, (x, y))
                if slot.quantity > 1:
                    q_surf = font.render(str(slot.quantity), True, (255, 255, 255))
                    surface.blit(q_surf, (x + ICON_SIZE - q_surf.get_width(), y + ICON_SIZE - q_surf.get_height()))
                
                hotspots.append(ClickableZone(r, f"look {slot.item.name}", data=slot.item))
            
            x += col_w
            current_col += 1
            if current_col >= cols:
                current_col = 0
                x = padding
                y += row_h

    else:
        row_h = ICON_SIZE + 2
        for slot in player.inventory.slots:
            if not slot.item: continue
            item = slot.item
            row_rect = pygame.Rect(0, y, surface.get_width(), row_h)

            icon = get_item_icon(item)
            surface.blit(icon, (padding, y))
            
            name_str = item.name
            if slot.quantity > 1: name_str += f" (x{slot.quantity})"
            
            text_y = y + (ICON_SIZE // 2) - 7 
            hotspots.append(ClickableZone(row_rect, f"look {item.name}", data=item))
            
            surface.blit(font.render(name_str, True, TEXT_COLOR), (padding + ICON_SIZE + 5, text_y))
            y += row_h + 2

def render_hostiles_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    world = context.get("world")
    player = context.get("player")
    if not world or not player: return
    font = get_font(14)
    y, padding = 5, 5
    
    npcs = world.get_current_room_npcs(player)
    hostiles = [n for n in npcs if n.faction == 'hostile']
    
    if not hostiles:
        surface.blit(font.render("(None)", True, (100, 100, 100)), (padding, y))
        return

    for npc in hostiles:
        txt = f"- {npc.name} ({int(npc.health)}/{npc.max_health})"
        _draw_clickable_text(surface, font, txt, padding, y, (255, 150, 150), f"attack {npc.name}", hotspots, data=npc)
        y += 16

def render_friendlies_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    world = context.get("world")
    player = context.get("player")
    if not world or not player: return
    font = get_font(14)
    y, padding = 5, 5
    
    npcs = world.get_current_room_npcs(player)
    friendlies = [n for n in npcs if n.faction != 'hostile']
    
    if not friendlies:
        surface.blit(font.render("(None)", True, (100, 100, 100)), (padding, y))
        return

    for npc in friendlies:
        txt = f"- {npc.name}"
        if hasattr(npc, "ai_state") and "current_activity" in npc.ai_state:
            txt += f" ({npc.ai_state['current_activity']})"
        _draw_clickable_text(surface, font, txt, padding, y, (200, 255, 200), f"look {npc.name}", hotspots, data=npc)
        y += 16

def render_quests_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return
    font = get_font(14)
    y, padding = 5, 5
    
    active = [q for q in player.runtime_state.quests.active.values() if q.get("state") in ["active", "ready_to_complete"]]
    
    if not active:
        surface.blit(font.render("(No active quests)", True, (100, 100, 100)), (padding, y))
        return

    for q in active:
        title = q.get("title", "Quest")
        color = TEXT_COLOR
        if q.get("state") == "ready_to_complete":
            color = (100, 255, 100)
            title = "! " + title
        if len(title) > 28: title = title[:25] + "..."
        
        # Display current stage info if possible
        qm = context["game"].world.quest_manager
        obj = qm.get_active_objective(q)
        desc = "Task"
        if obj:
             q_type = obj.get("type")
             if q_type == "kill": desc = "Hunt"
             elif q_type == "fetch": desc = "Gather"
             elif q_type == "deliver": desc = "Deliver"
             elif q_type == "scout": desc = "Scout"
        
        # Draw Title
        _draw_clickable_text(surface, font, title, padding, y, color, "journal", hotspots)
        y += 16
        
        # Draw Type/Desc tiny
        tiny_font = get_font(12)
        surface.blit(tiny_font.render(f"  {desc}", True, (150,150,150)), (padding, y))
        y += 14

def render_effects_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    if not player: return
    font = get_font(14)
    y, padding = 5, 5

    if not player.active_effects:
        surface.blit(font.render("(No effects)", True, (100, 100, 100)), (padding, y))
        return

    for eff in sorted(player.active_effects, key=lambda e: e.get("name", "z")):
        name = eff.get('name', 'Unknown')
        dur = f"{eff.get('duration_remaining', 0):.0f}s"
        color = (255, 100, 100) if eff.get("type") == "dot" else (100, 255, 100)
        
        surface.blit(font.render(f"{name} ({dur})", True, color), (padding, y))
        y += 18

def render_topics_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    world = context.get("world")
    game = context.get("game")
    if not player or not world or not game: return

    manager = game.knowledge_manager
    
    target_npc = None
    if player.trading_with:
        target_npc = world.get_npc(player.trading_with)
        if target_npc and (target_npc.current_region_id != player.current_region_id or target_npc.current_room_id != player.current_room_id):
            target_npc = None
    elif player.last_talked_to:
        candidate = world.get_npc(player.last_talked_to)
        if candidate and candidate.current_region_id == player.current_region_id and candidate.current_room_id == player.current_room_id:
            target_npc = candidate
            
    font = get_font(14)
    y = 5
    padding = 5
    
    if not target_npc:
        surface.blit(font.render("(No active conversation)", True, (150, 150, 150)), (padding, y))
        surface.blit(font.render("Use 'talk <npc>' to begin.", True, (100, 100, 100)), (padding, y + 20))
        return

    npc_name_surf = font.render(f"Speaking with: {target_npc.name}", True, (200, 200, 100))
    surface.blit(npc_name_surf, (padding, y))
    y += 20
    
    if target_npc.faction == "hostile":
        surface.blit(font.render("(Hostile)", True, (255, 50, 50)), (padding, y))
        return
    
    unasked_topics, asked_topics = manager.get_topics_for_npc(target_npc, player)
    
    def draw_list(topics, color_override=None):
        nonlocal y
        for topic_id in topics:
            display_name = manager.topics[topic_id].get("display_name", topic_id.replace("_", " ").title())
            # LOGIC CHANGE: Include Name in command
            cmd = f"ask {target_npc.name} {topic_id}"
            color = color_override if color_override else TEXT_COLOR
            _draw_clickable_text(surface, font, f"- {display_name}", padding, y, color, cmd, hotspots)
            y += 18

    if unasked_topics:
        surface.blit(font.render("New Topics:", True, (100, 255, 100)), (padding, y))
        y += 16
        draw_list(unasked_topics, (255, 255, 255))
        y += 5

    if asked_topics:
        surface.blit(font.render("Discussed:", True, (150, 150, 150)), (padding, y))
        y += 16
        draw_list(asked_topics, (120, 120, 120))
        
    if not unasked_topics and not asked_topics:
        surface.blit(font.render("(They have nothing to say)", True, (150, 150, 150)), (padding, y))

def render_collections_content(surface: pygame.Surface, context: dict, hotspots: List[ClickableZone]):
    player = context.get("player")
    game = context.get("game")
    if not player or not game: return

    manager = game.collection_manager
    font = get_font(14)
    y = 5
    padding = 5
    
    active_cols = [cid for cid in manager.collections if cid in player.collections_progress]
    
    if not active_cols:
        surface.blit(font.render("(No active collections)", True, (150, 150, 150)), (padding, y))
        return

    for col_id in active_cols:
        col_def = manager.collections[col_id]
        name = col_def.get("name", col_id)
        
        found = player.collections_progress.get(col_id, [])
        total = col_def.get("items", [])
        is_done = player.collections_completed.get(col_id, False)
        
        # Clickable Header
        color = (255, 215, 0) if is_done else TEXT_COLOR
        # Use new command
        cmd = f"collection {col_id}"
        _draw_clickable_text(surface, font, f"{name}", padding, y, color, cmd, hotspots)
        y += 18
        
        # Progress Bar
        bar_w = surface.get_width() - (padding * 2)
        bar_h = 6
        pct = len(found) / len(total) if total else 0
        
        pygame.draw.rect(surface, (60, 60, 60), (padding, y, bar_w, bar_h))
        pygame.draw.rect(surface, (100, 200, 100), (padding, y, int(bar_w * pct), bar_h))
        
        count_surf = get_font(12).render(f"{len(found)}/{len(total)}", True, (200, 200, 200))
        surface.blit(count_surf, (padding + bar_w - count_surf.get_width(), y - 14))
        
        y += 12
