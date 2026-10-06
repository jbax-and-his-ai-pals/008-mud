# engine/npcs/pacing.py
"""The rhythm of a fight: how fast every creature but the player acts, and how they take turns.

The player is the quick one; their own cooldown is not touched. Everyone else (monsters, allies, companions,
summons) acts on the cooldown they were given, stretched by `combat.pacing.npc_cooldown_scale`, and never
within `combat.pacing.action_gap` seconds of another creature's action in the same room, so a crowd's blows
arrive one after another rather than all in the same instant. A world with no `pacing` section behaves as it
always did.
"""

from typing import Any, Tuple

DEFAULT_SCALE = 1.0
DEFAULT_GAP = 0.0
PACING_KEYS = ("npc_cooldown_scale", "action_gap")
SCALE_RANGE = (1.0, 10.0)
GAP_RANGE = (0.0, 10.0)


def _number(value: Any, default: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        return default
    return float(value)


def settings(world: Any) -> Tuple[float, float]:
    """(cooldown scale, action gap in seconds) for this world."""
    combat = world.ruleset_section("combat") if hasattr(world, "ruleset_section") else {}
    section = combat.get("pacing") if isinstance(combat, dict) else None
    if not isinstance(section, dict):
        return DEFAULT_SCALE, DEFAULT_GAP
    return (_number(section.get("npc_cooldown_scale"), DEFAULT_SCALE, *SCALE_RANGE),
            _number(section.get("action_gap"), DEFAULT_GAP, *GAP_RANGE))


def cooldown_of(world: Any, seconds: float) -> float:
    """A creature's own pause between actions, stretched by the world's scale."""
    return float(seconds) * settings(world)[0]


def _room_key(npc: Any) -> Tuple[Any, Any]:
    return (getattr(npc, "current_region_id", None), getattr(npc, "current_room_id", None))


WAITING_FORGOTTEN_AFTER = 3.0   # a creature that has not asked for the beat in this long no longer holds a place in the line


def room_is_open(world: Any, npc: Any, now: float) -> bool:
    """False while another creature acted in this room less than `action_gap` seconds ago, or while one that has been
    waiting longer for the beat is ahead in the line (so a creature last in the room's order is not starved)."""
    gap = settings(world)[1]
    if gap <= 0:
        return True
    key = _room_key(npc)
    waiting = getattr(world, "combat_waiting", None)
    if waiting is None:
        waiting = world.combat_waiting = {}
    line = waiting.setdefault(key, {})
    for other_id in [i for i, (_first, seen) in line.items() if now - seen > WAITING_FORGOTTEN_AFTER]:
        del line[other_id]
    first_asked = line.get(npc.obj_id, (now, now))[0]
    line[npc.obj_id] = (first_asked, now)
    last = getattr(world, "combat_beats", {}).get(key)
    if last is not None and now - last < gap:
        return False
    ahead = min(line.items(), key=lambda item: (item[1][0], item[0]))[0]
    return ahead == npc.obj_id


def note_action(world: Any, npc: Any, now: float) -> None:
    """Record that `npc` acted in its room just now (and is no longer waiting)."""
    if settings(world)[1] <= 0:
        return
    beats = getattr(world, "combat_beats", None)
    if beats is None:
        beats = world.combat_beats = {}
    beats[_room_key(npc)] = now
    getattr(world, "combat_waiting", {}).get(_room_key(npc), {}).pop(npc.obj_id, None)
