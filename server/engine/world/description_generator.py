# engine/world/description_generator.py
from typing import TYPE_CHECKING, Dict, Any, List
from engine.config import (
    FORMAT_TITLE, FORMAT_RESET, FORMAT_ERROR, FORMAT_HIGHLIGHT, 
    FORMAT_GRAY, FORMAT_CATEGORY
)
from engine.utils.utils import format_name_for_display, get_article, simple_plural

if TYPE_CHECKING:
    from engine.world.world import World

def generate_room_description(world: 'World', minimal: bool = False, player=None) -> str:
    """
    Generates the formatted text description of the player's current location.
    Accepts an explicit player to support multiplayer sessions where world.player
    may refer to the wrong session's character.
    """
    player = player or world.resolve_reference_player()
    if not player or not world.game:
        return "You are not yet in the world."

    current_region_id = player.current_region_id
    current_room_id = player.current_room_id
    current_room = world.get_room_for_player(player)
    current_region = world.get_region(current_region_id)
    
    if not current_room or not current_region: 
        return f"{FORMAT_ERROR}You are nowhere.{FORMAT_RESET}"
    
    # 1. Header
    title = f"{FORMAT_TITLE}[{current_region.name.upper()} - {current_room.name.upper()}]{FORMAT_RESET}\n\n"
    
    # 2. Environment Context
    time_period = world.game.time_manager.current_time_period
    # A room may declare a local climate for authored extremes (for example,
    # a permanently snowy summit). Otherwise it inherits world weather.
    weather = current_room.get_property("weather", world.game.weather_manager.current_weather)
    
    if not current_region_id or not current_room_id:
        return f"{FORMAT_ERROR}Location Error{FORMAT_RESET}"

    is_outdoors = world.is_location_outdoors(current_region_id, current_room_id)
    
    # 3. Base Description
    room_desc = current_room.get_full_description(time_period, weather, is_outdoors=is_outdoors)

    # 4. Quest Visual Overrides (e.g. secret doors becoming visible)
    if player.runtime_state.quests is not None and player.runtime_state.quests.active:
        for quest_data in player.runtime_state.quests.active.values():
            entry_point = quest_data.get("entry_point")
            if (quest_data.get("state") == "active" and entry_point and
                entry_point.get("region_id") == current_region_id and
                entry_point.get("room_id") == current_room_id):
                
                extra_desc = entry_point.get("description_when_visible")
                if extra_desc:
                    room_desc += f"\n\n{FORMAT_HIGHLIGHT}{extra_desc}{FORMAT_RESET}"

    full_description = title + room_desc

    # 5. Entity Listings
    all_npcs_in_room = world.get_npcs_for_player(player)
    friendly_npcs = [npc for npc in all_npcs_in_room if npc.faction != "hostile"]
    hostile_npcs = [npc for npc in all_npcs_in_room if npc.faction == "hostile"]
    items_in_room = world.get_items_for_player(player)

    # --- FRIENDLY NPCs ---
    if friendly_npcs or not minimal:
        friendly_content_str = f"{FORMAT_GRAY}(None){FORMAT_RESET}"
        if friendly_npcs:
            friendly_npc_list = []
            for npc in friendly_npcs:
                # format_name_for_display adds the [[CMD:look...]] tags automatically
                formatted_name = format_name_for_display(player, npc, start_of_sentence=False)
                
                status_suffix = ""
                if npc.in_combat:
                    status_suffix = f" {FORMAT_ERROR}(Fighting!){FORMAT_RESET}"
                elif hasattr(npc, "ai_state") and "current_activity" in npc.ai_state:
                    status_suffix = f" ({npc.ai_state['current_activity']})"
                
                friendly_npc_list.append(f"{formatted_name}{status_suffix}")
            friendly_content_str = ", ".join(friendly_npc_list)
        full_description += f"\n\n{FORMAT_CATEGORY}People here:{FORMAT_RESET} {friendly_content_str}"

    # --- HOSTILE NPCs ---
    if hostile_npcs or not minimal:
        hostile_content_str = f"{FORMAT_GRAY}(None){FORMAT_RESET}"
        if hostile_npcs:
            hostile_npc_list = [f"{format_name_for_display(player, npc)}" for npc in hostile_npcs]
            hostile_content_str = ", ".join(hostile_npc_list)
        full_description += f"\n{FORMAT_CATEGORY}Hostiles:{FORMAT_RESET} {hostile_content_str}"

    # --- ITEMS ---
    if items_in_room or not minimal:
        item_content_str = f"{FORMAT_GRAY}(None){FORMAT_RESET}"
        if items_in_room:
            item_counts: Dict[str, Dict[str, Any]] = {}
            for item in items_in_room:
                item_key = item.obj_id
                # Differentiate procedural items (e.g. scrolls that teach
                # different spells) so distinct instances don't merge into
                # one stack entry. A template opts in by declaring which of
                # its own properties makes instances distinct, via
                # properties.procedural_disambiguation_property.
                if item.get_property("is_procedural"):
                    disambiguation_prop = item.get_property("procedural_disambiguation_property")
                    if disambiguation_prop:
                        disambiguation_value = item.get_property(disambiguation_prop)
                        if disambiguation_value: item_key += f"_{disambiguation_value}"
                
                if item_key not in item_counts:
                    item_counts[item_key] = {"name": item.name, "count": 0}
                item_counts[item_key]["count"] += 1

            item_message_parts = []
            for data in sorted(item_counts.values(), key=lambda x: x['name']):
                name = data['name']
                count = data['count']
                
                # Add Clickable Tags for Items
                click_start = f"[[CMD:look {name}]]"
                click_end = "[[/CMD]]"
                formatted_name = f"{click_start}{FORMAT_CATEGORY}{name}{FORMAT_RESET}{click_end}"
                
                if count == 1:
                    item_message_parts.append(f"{get_article(name)} {formatted_name}")
                else:
                    plural_name = simple_plural(name)
                    formatted_plural = f"{click_start}{FORMAT_CATEGORY}{plural_name}{FORMAT_RESET}{click_end}"
                    item_message_parts.append(f"{count} {formatted_plural}")
                    
            item_content_str = ", ".join(item_message_parts)
        full_description += f"\n{FORMAT_CATEGORY}Items:{FORMAT_RESET} {item_content_str}"
    
    return full_description
