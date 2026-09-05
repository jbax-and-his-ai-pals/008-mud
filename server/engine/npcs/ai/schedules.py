# engine/npcs/ai/schedules.py
"""
Assigns dynamic daily schedules to NPCs.

This module has no built-in notion of "merchant", "tavern", or any other
setting-specific vocabulary -- that all comes from the content set's
"npc_schedules" ruleset section. A content set that wants auto-scheduled
NPCs declares its own roles, room categories, and schedules there; a
content set that omits the section simply gets no auto-scheduling (NPCs
can still carry an explicit "schedule" on their template instead).

Expected ruleset shape (see content_sets/fantasy_frontier/rules/ruleset.json
for a worked example):

    "npc_schedules": {
        "excluded_name_keywords": ["guard"],
        "room_categories": {"homes": ["home", "cottage"], ...},
        "roles": [
            {
                "id": "merchant",
                "template_keywords": ["merchant", "shopkeeper"],
                "location_slots": {
                    "work": {"type": "property_or_self", "property": "work_location"},
                    "home": {"type": "category", "categories": ["homes"], "exclude": "work", "fallback": "work"}
                },
                "schedule": {
                    "8": {"activity": "opening shop", "slot": "work"},
                    "22": {"activity": "sleeping", "slot": "home"}
                }
            }
        ]
    }

Location slot types:
  - "self": the NPC's own home_region_id/home_room_id.
  - "property_or_self": reads a "region_id:room_id" string from an NPC
    property (falls back to "self" if absent/malformed).
  - "category": a random room from one or more room_categories (falls back
    to another named slot, given via "fallback", if the category is empty).
    "exclude" names another already-resolved slot to avoid picking the same
    room for both (e.g. so home and work aren't identical).

Slots are resolved in declaration order, so a slot referenced by an
"exclude" or "fallback" must be declared earlier in "location_slots".
"""
import random
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.world.world import World


def initialize_npc_schedules(world: 'World'):
    """Main entry point: assign schedules to NPCs per the content set's ruleset."""
    if not world:
        return

    config = world.ruleset_section("npc_schedules")
    roles = config.get("roles")
    if not isinstance(roles, list) or not roles:
        return

    available_rooms = _collect_available_rooms(world)
    if not available_rooms:
        return

    room_categories = config.get("room_categories", {})
    excluded_name_keywords = [str(k).lower() for k in config.get("excluded_name_keywords", [])]
    locale_spaces = _designate_locale_spaces(available_rooms, room_categories)

    for npc in world.npcs.values():
        if npc.faction in ["hostile", "player_minion"]:
            continue
        if any(keyword in npc.name.lower() for keyword in excluded_name_keywords):
            continue
        if not npc.template_id:
            continue

        role = _match_role(npc.template_id, roles)
        if role is None:
            continue

        if not hasattr(npc, "ai_state"):
            npc.ai_state = {}
        if "original_behavior_type" not in npc.ai_state:
            npc.ai_state["original_behavior_type"] = getattr(npc, "behavior_type", "wanderer")

        npc.schedule = _build_schedule(npc, role, locale_spaces)
        npc.behavior_type = "scheduled"
        npc.last_moved = 0


def _match_role(template_id: str, roles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for role in roles:
        keywords = role.get("template_keywords", [])
        if any(keyword in template_id for keyword in keywords):
            return role
    return None


def _collect_available_rooms(world: 'World'):
    available_rooms = []
    for region_id, region in world.regions.items():
        for room_id, room in region.rooms.items():
            available_rooms.append({
                "region_id": region_id, "room_id": room_id,
                "room_name": room.name, "properties": getattr(room, "properties", {})
            })
    return available_rooms


def _designate_locale_spaces(available_rooms, room_categories: Dict[str, List[str]]):
    spaces: Dict[str, List[dict]] = {category: [] for category in room_categories}
    for room_info in available_rooms:
        room_name = room_info["room_name"].lower()
        for category, keywords in room_categories.items():
            if any(keyword in room_name for keyword in keywords):
                if room_info not in spaces[category]:
                    spaces[category].append(room_info)

    civic_fallback = spaces.get("civic_area") or available_rooms
    for category in spaces:
        if not spaces[category] and civic_fallback:
            spaces[category] = random.sample(civic_fallback, min(1, len(civic_fallback)))
    return spaces


def _get_random_location(locations, exclude_loc=None):
    if not locations:
        return None
    valid_locations = [loc for loc in locations if loc != exclude_loc]
    return random.choice(valid_locations) if valid_locations else random.choice(locations)


def _resolve_slot(npc, slot_def: Dict[str, Any], locale_spaces: Dict[str, List[dict]], resolved: Dict[str, dict]) -> dict:
    self_loc = {"region_id": npc.home_region_id, "room_id": npc.home_room_id}
    slot_type = slot_def.get("type", "self")

    if slot_type == "self":
        return self_loc

    if slot_type == "property_or_self":
        raw = npc.properties.get(slot_def.get("property", ""))
        if isinstance(raw, str) and ":" in raw:
            region_id, room_id = raw.split(":", 1)
            return {"region_id": region_id, "room_id": room_id}
        return self_loc

    if slot_type == "category":
        candidates: List[dict] = []
        for category in slot_def.get("categories", []):
            candidates.extend(locale_spaces.get(category, []))
        exclude_loc = resolved.get(slot_def.get("exclude", "")) if slot_def.get("exclude") else None
        location = _get_random_location(candidates, exclude_loc=exclude_loc)
        if location is not None:
            return location
        fallback_name = slot_def.get("fallback")
        if fallback_name and fallback_name in resolved:
            return resolved[fallback_name]
        return self_loc

    return self_loc


def _build_schedule(npc, role: Dict[str, Any], locale_spaces: Dict[str, List[dict]]) -> Dict[str, dict]:
    resolved: Dict[str, dict] = {}
    for slot_name, slot_def in role.get("location_slots", {}).items():
        resolved[slot_name] = _resolve_slot(npc, slot_def, locale_spaces, resolved)

    schedule: Dict[str, dict] = {}
    for hour, entry in role.get("schedule", {}).items():
        location = resolved.get(entry.get("slot"), {"region_id": npc.home_region_id, "room_id": npc.home_room_id})
        schedule[hour] = {"activity": entry.get("activity", "idle"), **location}
    return schedule
