# engine/world/placements.py
"""What a room's authored NPC placement says about the creature it stands for.

A room lists the creatures it starts with (`initial_npcs`); each entry names a template and
may carry `overrides` that change that one placement (a weakened encounter, a guide who does
not wander). The loader applies them when the world is built. Bringing a defeated creature
back has to apply the same ones, and has to know whether the room placed the creature at all
(a hostile the ambient spawner made is refilled by the spawner, not by this), so both read
the placement through here.
"""
from typing import Any, Dict, Optional

# The override keys a placement may change; location is owned by the room, not by an override.
PLACEMENT_OVERRIDE_KEYS = (
    "name", "level", "health", "max_health", "mana", "max_mana", "behavior_type",
    "properties_override", "patrol_points", "patrol_index",
)


def placement_overrides(npc_ref: Dict[str, Any]) -> Dict[str, Any]:
    raw = npc_ref.get("overrides", {})
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in PLACEMENT_OVERRIDE_KEYS if key in raw}


def find_placement(world, region_id: Optional[str], room_id: Optional[str], instance_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The entry in `room_id`'s `initial_npcs` whose `instance_id` is `instance_id`, else None.

    A placement with no `instance_id` gets a random one when the world is built, so it can
    never be matched here: that creature is treated as not placed.
    """
    if not (region_id and room_id and instance_id):
        return None
    region = world.get_region(region_id) if hasattr(world, "get_region") else None
    room = region.get_room(room_id) if region is not None else None
    for ref in getattr(room, "initial_npc_refs", None) or []:
        if isinstance(ref, dict) and ref.get("instance_id") == instance_id:
            return ref
    return None


def authored_respawn_cooldown(world, template_id: Optional[str], placement: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """The `respawn_cooldown` an author wrote for this creature, or None when nobody did.

    Every creature carries a cooldown at runtime (a default is filled in), so only the
    authored source says whether the author meant one: the placement's `properties_override`
    first, then the template's `properties`. `-1` means never.
    """
    sources = []
    if isinstance(placement, dict):
        override = placement_overrides(placement).get("properties_override")
        if isinstance(override, dict):
            sources.append(override)
    template = (getattr(world, "npc_templates", None) or {}).get(template_id) or {}
    if isinstance(template.get("properties"), dict):
        sources.append(template["properties"])
    for properties in sources:
        value = properties.get("respawn_cooldown")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
