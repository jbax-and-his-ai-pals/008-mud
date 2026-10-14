# engine/core/level_table.py
"""A level table: what a character *is* at each level, written out, instead of a growth rule.

`advancement.level_up` (`level_growth.py`) says what a level adds. Some games say what a level is: the stats, health and
magic pool at level 5 are these numbers, and the experience to the next level is that number. A set says so with

    "advancement": {
        "level_table": [
            {"xp": 7,  "stats": {"strength": 4, "agility": 4}, "max_health": 15, "max_mana": 0},
            {"xp": 16, "stats": {"strength": 5, "agility": 4}, "max_health": 22, "max_mana": 0},
            {"stats": {"strength": 7, "agility": 6}, "max_health": 24, "max_mana": 5}
        ]
    }

Row 0 is level 1. `xp` is what it costs to reach the next level; the last row has none and is the level cap. A row's `stats`
are absolute values for the stats it names (the rest are left as they are); `max_health` and `max_mana` are absolute too.
A row's `spells` (ability ids) are learned on reaching that level. With a table the growth rule is not used, and the table is applied
to a new character (level 1) and at every level reached.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

ROW_KEYS = ("xp", "stats", "max_health", "max_mana", "spells")
CAP_COST = 10 ** 9   # the cost of the level after the last: out of reach, so the character stays at the cap


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def table_of(world: Any) -> List[Dict[str, Any]]:
    """The set's level table (a list of rows), or an empty list when it has none or it is unusable."""
    try:
        section = world.ruleset_section("advancement") if world is not None else {}
    except Exception:  # noqa: BLE001 - a world without rules has no table
        return []
    table = section.get("level_table") if isinstance(section, dict) else None
    if not isinstance(table, list) or not table or not all(isinstance(row, dict) for row in table):
        return []
    return table


def row_for(world: Any, level: int) -> Optional[Dict[str, Any]]:
    """The row for `level` (1 is the first), or None when the set has no table."""
    table = table_of(world)
    if not table:
        return None
    return table[max(0, min(int(level), len(table)) - 1)]


def cost_to_next(world: Any, level: int) -> Optional[int]:
    """What reaching `level + 1` costs, from the table; None without one. At the last row it is out of reach."""
    table = table_of(world)
    if not table:
        return None
    if int(level) >= len(table):
        return CAP_COST
    cost = table[int(level) - 1].get("xp")
    return int(cost) if _number(cost) and cost > 0 else CAP_COST


def learn_row_spells(player: Any, level: int) -> list:
    """Teach what the row for `level` names; the lines the player reads about it."""
    row = row_for(getattr(player, "world", None), level)
    lines: list = []
    for spell_id in (row.get("spells") if isinstance(row, dict) and isinstance(row.get("spells"), list) else []):
        learned, text = player.learn_spell(str(spell_id), award=False)
        if learned:
            lines.append(text)
    return lines


def apply_row(player: Any, level: int, world: Any = None) -> bool:
    """Make `player` what the table says a character of `level` is. Health and the pool rise by the difference. False without a table."""
    row = row_for(world if world is not None else getattr(player, "world", None), level)
    if row is None:
        return False
    stats = row.get("stats")
    if isinstance(stats, dict):
        for name, value in stats.items():
            if _number(value):
                player.stats[name] = value
    max_health = row.get("max_health")
    if _number(max_health) and max_health > 0:
        gained = int(max_health) - int(player.max_health)
        player.max_health = int(max_health)
        player.health = max(1, min(player.max_health, int(player.health) + max(0, gained)))
    magic = getattr(getattr(player, "runtime_state", None), "magic", None)
    max_mana = row.get("max_mana")
    if magic is not None and _number(max_mana) and max_mana >= 0:
        gained = int(max_mana) - int(magic.max_mana)
        magic.max_mana = int(max_mana)
        magic.mana = max(0, min(magic.max_mana, int(magic.mana) + max(0, gained)))
    return True
