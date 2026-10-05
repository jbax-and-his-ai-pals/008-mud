# engine/npcs/combat_detail.py
"""How much of a fight a player reads: `full`, `normal` or `brief` (the `combat` command sets it).

* `full` is every blow of every creature, as it always was, and is where every player starts.
* `normal` keeps what matters in full and folds the rest into a short summary of what happened in the last
  few seconds ("Lucan hits a sand grub for 7. A sand grub hits Ryn for 15").
* `brief` keeps only what matters.

What matters, always shown in full: a blow at the player, a death, a spell, song or special attack, and a
friend knocked low. The rest is routine: an ally's plain blow, an enemy's plain blow at an ally, two other
creatures trading blows. The numbers stay in the text at every level. The choice is the player's and is kept
with the character (`flags["_pref.combat_detail"]`).
"""

import re
from typing import Any, Dict, List, Optional

LEVELS = ("full", "normal", "brief")
DEFAULT_LEVEL = "full"
FLAG = "_pref.combat_detail"
WINDOW_SECONDS = 3.0   # how long routine blows are gathered before one line tells them
LOW_HEALTH = 0.4       # a friend below this fraction of health is worth a line of their own


def level_of(player: Any) -> str:
    flags = getattr(player, "flags", None)
    value = flags.get(FLAG) if isinstance(flags, dict) else None
    return value if value in LEVELS else DEFAULT_LEVEL


def set_level(player: Any, level: str) -> bool:
    if level not in LEVELS or not isinstance(getattr(player, "flags", None), dict):
        return False
    if level == DEFAULT_LEVEL:
        player.flags.pop(FLAG, None)   # the default writes nothing
    else:
        player.flags[FLAG] = level
    return True


def _is_low_friend(target: Any, viewer: Any, world: Any) -> bool:
    from engine.world import factions

    max_health = getattr(target, "max_health", 0) or 0
    if target is viewer or max_health <= 0 or not factions.is_player_side(target, world):
        return False
    return getattr(target, "health", max_health) < LOW_HEALTH * max_health


def is_routine(action_result: Dict[str, Any], npc: Any, target: Any, viewer: Any, world: Any) -> bool:
    """A plain blow nobody needs a line of their own for."""
    if not action_result.get("routine") or action_result.get("target_defeated"):
        return False
    if target is viewer:
        return False
    return not _is_low_friend(target, viewer, world)


def _entry(viewer: Any, npc: Any, target: Any, action_result: Dict[str, Any]) -> str:
    from engine.utils.utils import format_name_for_display

    damage = int(action_result.get("damage", 0) or 0)
    name = format_name_for_display(viewer, npc, start_of_sentence=True)
    what = format_name_for_display(viewer, target, start_of_sentence=False)
    return "%s hits %s for %d" % (name, what, damage) if damage > 0 else "%s misses %s" % (name, what)


_AFFECTED = re.compile(r"^(?P<who>.+?)(?: \([^)]*\))? is affected by (?P<what>.+?)\.?$")


def fold_effects(message: str) -> str:
    """One "X is affected by Sleep." line per creature becomes one line for the lot ("2 enemies are affected by Sleep.")."""
    lines = message.split("\n")
    counts: Dict[str, int] = {}
    for line in lines:
        found = _AFFECTED.match(re.sub(r"\[\[[^\]]*\]\]", "", line).strip())
        if found:
            counts[found.group("what")] = counts.get(found.group("what"), 0) + 1
    folded, told = [], set()
    for line in lines:
        found = _AFFECTED.match(re.sub(r"\[\[[^\]]*\]\]", "", line).strip())
        if not found or counts[found.group("what")] < 2:
            folded.append(line)
        elif found.group("what") not in told:
            told.add(found.group("what"))
            folded.append("%d enemies are affected by %s." % (counts[found.group("what")], found.group("what")))
    return "\n".join(folded)


def _pending(world: Any) -> Dict[str, Dict[str, Any]]:
    pending = getattr(world, "combat_digest", None)
    if pending is None:
        pending = world.combat_digest = {}
    return pending


def _text(entries: List[str]) -> str:
    return " ".join(entry + "." for entry in entries)


def shape(world: Any, viewer: Any, npc: Any, target: Any, action_result: Dict[str, Any], message: str, now: float) -> Optional[str]:
    """What the viewer reads of one creature's action, at their level of detail (None: nothing)."""
    level = level_of(viewer)
    if level == "full":
        return message
    pending = _pending(world)
    if not is_routine(action_result, npc, target, viewer, world):
        held = pending.pop(viewer.obj_id, None)   # what came before is told first, so the order stays true
        message = fold_effects(message)
        if held and level == "normal":
            return _text(held["entries"]) + "\n" + message
        return message
    if level == "normal":
        slot = pending.setdefault(viewer.obj_id, {"first": now, "entries": [], "viewer": viewer})
        slot["entries"].append(_entry(viewer, npc, target, action_result))
    return None


def routine_line(world: Any, viewer: Any, text: str, now: float) -> Optional[str]:
    """A line that only says who has turned on whom ("Lucan intercepts a grub!"): told at `full`, folded into the
    next summary at `normal`, dropped at `brief`."""
    level = level_of(viewer)
    if level == "full" or viewer is None:
        return text
    if level == "normal":
        slot = _pending(world).setdefault(viewer.obj_id, {"first": now, "entries": [], "viewer": viewer})
        slot["entries"].append(text.rstrip("!. "))
    return None


def flush_due(world: Any, now: float, force: bool = False) -> None:
    """Tell the summaries whose window has passed (called every world tick)."""
    pending = getattr(world, "combat_digest", None)
    if not pending:
        return
    for key in list(pending):
        slot = pending[key]
        if not (force or now - slot["first"] >= WINDOW_SECONDS):
            continue
        del pending[key]
        viewer = slot["viewer"]
        if getattr(viewer, "is_alive", False) and slot["entries"]:
            world.notify_player(viewer, _text(slot["entries"]))
