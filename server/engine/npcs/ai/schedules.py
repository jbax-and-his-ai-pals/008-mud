# engine/npcs/ai/schedules.py
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.world.world import World

def initialize_npc_schedules(world: 'World'):
    """
    Main function to assign dynamic schedules to all non-hostile, non-minion NPCs.
    This is called on new game creation and game load.
    """
    if not world: return

    available_rooms = _collect_available_rooms(world)
    if not available_rooms: return

    town_spaces = _designate_locale_spaces(world, available_rooms)

    for obj_id, npc in world.npcs.items():
        if npc.faction in ["hostile", "player_minion"] or "guard" in npc.name.lower():
            continue

        if not npc.template_id:
            continue 

        if not hasattr(npc, "ai_state"): npc.ai_state = {}
        if "original_behavior_type" not in npc.ai_state:
            npc.ai_state["original_behavior_type"] = getattr(npc, "behavior_type", "wanderer")

        schedule_created = False
        if "merchant" in npc.template_id or "shopkeeper" in npc.template_id:
            _create_merchant_schedule(npc, town_spaces)
            schedule_created = True
        elif "bartender" in npc.template_id:
            _create_bartender_schedule(npc, town_spaces)
            schedule_created = True
        elif "elder" in npc.template_id:
            _create_elder_schedule(npc, town_spaces)
            schedule_created = True
        elif "villager" in npc.template_id:
            _create_villager_schedule(npc, town_spaces)
            schedule_created = True
        
        if schedule_created:
            npc.behavior_type = "scheduled"
            npc.last_moved = 0 

def _collect_available_rooms(world: 'World'):
    available_rooms = []
    for region_id, region in world.regions.items():
        for room_id, room in region.rooms.items():
            available_rooms.append({
                "region_id": region_id, "room_id": room_id,
                "room_name": room.name, "properties": getattr(room, "properties", {})
            })
    return available_rooms

def _designate_locale_spaces(world: 'World', available_rooms):
    town_spaces = {"homes": [], "shops": [], "taverns": [], "markets": [], "civic_area": [], "gardens": [], "work_areas": [], "social_areas": []}
    keywords = {
        "homes": ["home", "house", "cottage"], "shops": ["shop", "store"],
        "taverns": ["tavern", "inn", "pub"], "markets": ["market", "bazaar"],
        "civic_area": ["square", "plaza", "center"], "gardens": ["garden", "park"],
        "work_areas": ["workshop", "forge", "mill"], "social_areas": ["hall", "meeting"]
    }
    for room_info in available_rooms:
        room_name = room_info["room_name"].lower()
        for space_type, key_list in keywords.items():
            if any(key in room_name for key in key_list):
                if room_info not in town_spaces[space_type]:
                    town_spaces[space_type].append(room_info)
    
    for space_type in town_spaces:
        if not town_spaces[space_type]:
            suitable_fallbacks = town_spaces["civic_area"] or available_rooms
            if suitable_fallbacks:
                town_spaces[space_type] = random.sample(suitable_fallbacks, min(1, len(suitable_fallbacks)))
    return town_spaces

def _get_random_location(locations, exclude_loc=None):
    if not locations: return None
    valid_locations = [loc for loc in locations if loc != exclude_loc]
    return random.choice(valid_locations) if valid_locations else random.choice(locations)

def _create_villager_schedule(npc, town_spaces):
    home = _get_random_location(town_spaces["homes"]) or {"region_id": npc.home_region_id, "room_id": npc.home_room_id}
    work_place = _get_random_location(town_spaces["work_areas"] + town_spaces["markets"], exclude_loc=home) or home
    social_spot = _get_random_location(town_spaces["taverns"] + town_spaces["civic_area"], exclude_loc=home) or home
    
    npc.schedule = {
        "7": {"activity": "waking up", **home},
        "8": {"activity": "eating", **home},
        "9": {"activity": "going to work", **work_place},
        "10": {"activity": "working", **work_place},
        "13": {"activity": "lunch break", **social_spot},
        "14": {"activity": "working", **work_place},
        "18": {"activity": "socializing", **social_spot},
        "21": {"activity": "relaxing", **home},
        "22": {"activity": "sleeping", **home}
    }

def _create_merchant_schedule(npc, town_spaces):
    shop_loc_str = npc.properties.get("work_location")
    if shop_loc_str and ":" in shop_loc_str:
        shop_region, shop_room = shop_loc_str.split(":")
        shop = {"region_id": shop_region, "room_id": shop_room}
    else:
        shop = {"region_id": npc.home_region_id, "room_id": npc.home_room_id}
    
    home = _get_random_location(town_spaces["homes"], exclude_loc=shop) or shop
    tavern = _get_random_location(town_spaces["taverns"]) or home

    npc.schedule = {
        "7": {"activity": "waking up", **home},
        "8": {"activity": "opening shop", **shop},
        "9": {"activity": "working", **shop},
        "17": {"activity": "closing up", **shop},
        "18": {"activity": "eating dinner", **tavern},
        "20": {"activity": "heading home", **home},
        "22": {"activity": "sleeping", **home}
    }

def _create_bartender_schedule(npc, town_spaces):
    tavern_loc_str = npc.properties.get("work_location")
    if tavern_loc_str and ":" in tavern_loc_str:
        tav_region, tav_room = tavern_loc_str.split(":")
        tavern = {"region_id": tav_region, "room_id": tav_room}
    else:
        tavern = {"region_id": npc.home_region_id, "room_id": npc.home_room_id}
    
    home = _get_random_location(town_spaces["homes"], exclude_loc=tavern) or tavern
    market = _get_random_location(town_spaces["markets"]) or tavern

    npc.schedule = {
        "9": {"activity": "waking up", **home},
        "11": {"activity": "getting supplies", **market},
        "12": {"activity": "preparing the bar", **tavern},
        "14": {"activity": "working", **tavern},
        "23": {"activity": "closing up", **tavern},
        "0": {"activity": "walking home", **home},
        "1": {"activity": "sleeping", **home}
    }

def _create_elder_schedule(npc, town_spaces):
    home = {"region_id": npc.home_region_id, "room_id": npc.home_room_id}
    square = _get_random_location(town_spaces["civic_area"]) or home
    garden = _get_random_location(town_spaces["gardens"]) or square
    
    npc.schedule = {
        "8": {"activity": "meditating", **home},
        "10": {"activity": "counseling villagers", **square},
        "15": {"activity": "walking in the garden", **garden},
        "17": {"activity": "returning home", **home},
        "21": {"activity": "sleeping", **home}
    }
