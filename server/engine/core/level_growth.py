# engine/core/level_growth.py
"""What a level is worth: how much each stat and the health pool grow when a player levels up.

The XP curve was always the content set's (`advancement.curve`); what a level *brings* was an
engine constant, the same +1 to every stat and the same base health for every game. A set can now
say its own in the ruleset:

    "advancement": {
        "level_up": {
            "stat_growth": {"default": 1, "strength": 2, "agility": 0},
            "health_base": 8
        }
    }

`stat_growth.default` is what every stat gains unless it is named; a named stat gains what it says
(0 for a stat that never grows). `health_base` is the flat part of a level's health; the part that
follows the health stat is unchanged. Anything not said plays as it always has.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from engine.config import PLAYER_LEVEL_HEALTH_BASE_INCREASE, PLAYER_LEVEL_UP_STAT_INCREASE

DEFAULT_STAT_GROWTH = PLAYER_LEVEL_UP_STAT_INCREASE
DEFAULT_HEALTH_BASE = PLAYER_LEVEL_HEALTH_BASE_INCREASE


def _non_negative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def level_up_settings(world: Any) -> Tuple[Dict[str, float], int]:
    """(per-stat growth with a "default" entry, flat health per level), engine defaults for what is not said."""
    section: Any = {}
    try:
        section = world.ruleset_section("advancement").get("level_up", {}) if world is not None else {}
    except Exception:  # noqa: BLE001 - a world without rules plays by the defaults
        section = {}
    section = section if isinstance(section, dict) else {}
    growth: Dict[str, float] = {"default": DEFAULT_STAT_GROWTH}
    raw_growth = section.get("stat_growth")
    if isinstance(raw_growth, dict):
        for stat, amount in raw_growth.items():
            if isinstance(stat, str) and _non_negative(amount):
                growth[stat] = amount
    health = section.get("health_base")
    return growth, (int(health) if _non_negative(health) else DEFAULT_HEALTH_BASE)


def growth_for(growth: Dict[str, float], stat: str) -> float:
    """What `stat` gains on a level."""
    return growth.get(stat, growth.get("default", DEFAULT_STAT_GROWTH))
