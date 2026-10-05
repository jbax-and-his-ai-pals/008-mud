# engine/npcs/companions.py
"""Companions: creatures that travel with a player and fight for them.

A summon is temporary and a party is other players. A companion is an authored NPC a
conversation recruits (`recruit` effect) and later releases (`dismiss`). It is the same
thing the minion AI already drives (follows its owner, joins the owner's fights, credits
the owner with kills), made permanent: `summon_duration` 0 and `is_summoned` false, so it
is neither timed out nor swept up when its owner dies.

There is no separate ledger. A companion is an NPC that carries `properties.companion`
and its owner's id in `properties.owner_id`, both saved with the NPC, so a restart brings
it back still bound to the character (whose id is stable). `companions_of` finds them.

A companion that is badly hurt in a fight falls back like any creature, and is then *recovering*: it keeps out of
fights, rests, and rejoins its owner (walking to find them if it must) once it has recovered to
`properties.rejoin_health` of its health (default 60%) and its owner is not fighting. Talking to it meanwhile can say so
(`companion_recovering`).

The cap is the ruleset's `companions.max` (default 1); a set that wants a party of three
says so. Recruiting past it is refused with a sentence, not an error.
"""
from typing import Any, List, Optional, Tuple

DEFAULT_MAX_COMPANIONS = 1
COMPANION_FACTION = "player_minion"
COMPANION_BEHAVIOR = "minion"
# Kept on the NPC so `dismiss` can put it back the way it was recruited from.
PRIOR_KEY = "companion_prior"
# A companion that has fallen back hurt (see the module note).
RECOVERING_KEY = "recovering"
DEFAULT_REJOIN_FRACTION = 0.6


def max_companions(world: Any) -> int:
    section = world.ruleset_section("companions") if hasattr(world, "ruleset_section") else {}
    value = section.get("max", DEFAULT_MAX_COMPANIONS) if isinstance(section, dict) else DEFAULT_MAX_COMPANIONS
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return DEFAULT_MAX_COMPANIONS
    return value


def is_companion(npc: Any) -> bool:
    properties = getattr(npc, "properties", None)
    return isinstance(properties, dict) and bool(properties.get("companion"))


def is_recovering(npc: Any) -> bool:
    properties = getattr(npc, "properties", None)
    return isinstance(properties, dict) and properties.get(RECOVERING_KEY) is True and is_companion(npc)


def rejoin_fraction(npc: Any) -> float:
    value = npc.properties.get("rejoin_health", DEFAULT_REJOIN_FRACTION)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
        return DEFAULT_REJOIN_FRACTION
    return float(value)


def begin_recovery(npc: Any) -> None:
    npc.properties[RECOVERING_KEY] = True


def recovery_step(npc: Any, world: Any, current_time: float, player: Any) -> Optional[str]:
    """One turn of a recovering companion: rest, and rejoin when well enough and the owner is not fighting.

    Returns what a player in the room is told (the companion rejoining), else None."""
    owner = world.get_player_by_id(npc.properties.get("owner_id")) if world is not None else None
    if owner is None:
        return None
    if not npc.in_combat:
        npc._handle_safe_zone_regen(current_time)   # resting, wherever it is
    owner_combat = owner.runtime_state.combat
    if npc.in_combat or (owner_combat is not None and owner_combat.in_combat):
        return None
    if npc.health < npc.max_health * rejoin_fraction(npc):
        return None
    npc.properties.pop(RECOVERING_KEY, None)
    if (npc.current_region_id, npc.current_room_id) == (owner.current_region_id, owner.current_room_id):
        return "%s has recovered and rejoins you." % npc.name
    if hasattr(world, "notify_player"):
        world.notify_player(owner, "%s has recovered and is coming to find you." % npc.name)
    return None


# A companion drinks a healing item from its own pack (`initial_inventory`) when its health falls below this fraction,
# and not again for this many seconds, so a fight is not one long swallowing.
POTION_THRESHOLD = 0.4
POTION_COOLDOWN = 8.0
LAST_POTION_KEY = "last_potion_at"


def _healing_item(npc: Any) -> Optional[Any]:
    inventory = getattr(npc, "inventory", None)
    for slot in getattr(inventory, "slots", None) or []:
        item = getattr(slot, "item", None)
        if item is not None and item.get_property("effect_type") == "heal" and item.get_property("uses", 1) > 0:
            return item
    return None


def drink_potion_if_hurt(npc: Any, world: Any, current_time: float) -> Optional[str]:
    """A hurt companion with a healing item in its pack drinks it. The line to tell, or None."""
    if not is_companion(npc) or is_recovering(npc) or not getattr(npc, "is_alive", False):
        return None
    if npc.health >= npc.max_health * POTION_THRESHOLD:
        return None
    if current_time - float(npc.properties.get(LAST_POTION_KEY, -1e9)) < POTION_COOLDOWN:
        return None
    item = _healing_item(npc)
    if item is None:
        return None
    gained = npc.heal(int(item.get_property("effect_value", 0) or 0))
    npc.properties[LAST_POTION_KEY] = current_time
    npc.inventory.remove_item(item.obj_id, 1)
    from engine.utils.articles import the

    return "%s drinks %s%s." % (npc.name, the(item.name), (" and recovers %d health" % gained) if gained else "")


def companions_of(world: Any, player: Any, *, alive_only: bool = True) -> List[Any]:
    """The NPCs bound to `player` as companions, in a stable order."""
    owner_id = getattr(player, "obj_id", None)
    if not owner_id or world is None:
        return []
    found = [
        npc for npc in getattr(world, "npcs", {}).values()
        if is_companion(npc) and npc.properties.get("owner_id") == owner_id and (npc.is_alive or not alive_only)
    ]
    return sorted(found, key=lambda npc: npc.obj_id)


def rebind_owner(world: Any, old_id: Optional[str], new_id: Optional[str]) -> int:
    """Move every companion bound to `old_id` to `new_id`: a character resumed on a new
    connection is the same character. Returns how many were rebound."""
    if not old_id or not new_id or old_id == new_id or world is None:
        return 0
    count = 0
    for npc in getattr(world, "npcs", {}).values():
        if is_companion(npc) and npc.properties.get("owner_id") == old_id:
            npc.properties["owner_id"] = new_id
            npc.owner_id = new_id
            count += 1
    return count


def recruit(world: Any, player: Any, npc: Any) -> Tuple[bool, str]:
    """Bind `npc` to `player`. Returns (recruited, what to tell the player)."""
    if npc is None or not getattr(npc, "is_alive", False):
        return False, "There is no one to recruit."
    if is_companion(npc):
        if npc.properties.get("owner_id") == player.obj_id:
            return False, "%s is already with you." % npc.name
        return False, "%s is with someone else." % npc.name
    if (npc.current_region_id, npc.current_room_id) != (player.current_region_id, player.current_room_id):
        return False, "%s is not here." % npc.name
    cap = max_companions(world)
    if len(companions_of(world, player)) >= cap:
        if not cap:
            return False, "There is no room for companions in this world."
        return False, "You cannot bring another with you (you may have %d companion%s)." % (cap, "" if cap == 1 else "s")
    npc.properties[PRIOR_KEY] = {"faction": npc.faction, "behavior_type": npc.behavior_type}
    npc.properties.update({"companion": True, "owner_id": player.obj_id, "summon_duration": 0, "move_cooldown": 2})
    npc.owner_id = player.obj_id
    npc.faction = COMPANION_FACTION
    npc.behavior_type = COMPANION_BEHAVIOR
    npc.move_cooldown = 2
    return True, "%s joins you." % npc.name


def dismiss(world: Any, player: Any, npc: Any) -> Tuple[bool, str]:
    """Release a companion where it stands, as it was before it joined."""
    if npc is None or not is_companion(npc) or npc.properties.get("owner_id") != getattr(player, "obj_id", None):
        return False, "That is not one of your companions."
    prior = npc.properties.pop(PRIOR_KEY, None) or {}
    npc.faction = prior.get("faction") or "friendly"
    npc.behavior_type = prior.get("behavior_type") or "stationary"
    for key in ("companion", "owner_id", "summon_duration"):
        npc.properties.pop(key, None)
    npc.owner_id = None
    return True, "%s stays behind." % npc.name


def travel_with(world: Any, player: Any, old_region_id: Optional[str], old_room_id: Optional[str]) -> List[str]:
    """Bring the player's companions that were standing with them to where they now are.

    Companions ignore exit gates, as NPCs do: they follow through a door the player has
    opened. Any that were not in the room (left behind, or still walking) are not moved;
    the minion AI walks them to their owner.
    """
    moved: List[str] = []
    for npc in companions_of(world, player):
        if (npc.current_region_id, npc.current_room_id) != (old_region_id, old_room_id):
            continue
        if is_recovering(npc):
            continue   # resting where it is; it comes to find its owner once it has recovered
        if (npc.current_region_id, npc.current_room_id) == (player.current_region_id, player.current_room_id):
            continue
        npc.current_region_id = player.current_region_id
        npc.current_room_id = player.current_room_id
        moved.append("%s follows you." % npc.name)
    return moved


def _where(world: Any, npc: Any) -> str:
    """", in The Fogwatch Inn": where a companion who is not here is, by the room's name."""
    try:
        region = world.get_region(npc.current_region_id)
        room = region.get_room(npc.current_room_id) if region else None
        name = str(getattr(room, "name", "") or "")
    except Exception:  # noqa: BLE001 - a line of text must never break the list
        name = ""
    return ", in %s" % name if name else ""


def party_lines(world: Any, player: Any) -> List[str]:
    """One line per companion, for the `companions` command."""
    lines = []
    for npc in companions_of(world, player):
        here = (npc.current_region_id, npc.current_room_id) == (player.current_region_id, player.current_room_id)
        place = "here" if here else "elsewhere%s" % _where(world, npc)
        if is_recovering(npc):
            place += ", recovering"
        lines.append("%s (level %d, %d/%d health, %s)" % (npc.name, npc.level, npc.health, npc.max_health, place))
    return lines
