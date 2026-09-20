"""Which stat fills which role, as the content set declares it.

Stats are the last system in the engine with no contract. `resources` says which
stat drives the ability pool and is read through `contracts/resources.py`; the
status line's list is declared under `ruleset.status.stats`; everything else
about stats was a stat *name* written into engine code, about thirty times across
fifteen files. The consequence was that a content set could not rename
`constitution`: health would keep reading a stat nobody had, find the default,
and produce a character whose physical stat did nothing at all.

This module resolves a **role** to the stat that fills it:

    health          how much punishment a body takes
    attack          how hard a weapon hits
    defence         how much physical damage is shrugged off
    evasion         how hard a body is to hit
    regeneration    how fast a body recovers between fights
    power           the stat an ability's own value scales with
    ability_power   a flat bonus added to every ability's value
    resistance      the flat reduction against a non-physical channel

As with `resources`, the naming is content and the *curve* is engine config: a
set says constitution drives health, and the engine's own numbers say how much
health per point. A set that declares nothing gets the engine's fantasy-flavoured
defaults, which is exactly the behaviour that shipped before this module existed,
so no set's numbers move until it says they should.

`stat_name` returns a *name*; `stat_for` returns a value. Callers that want a
number should nearly always use the second, because a name is only useful for
looking something up in the same stats dictionary.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# The roles the engine asks about, with the stat each one falls back to. The
# fallback is a *name*, which is the one place this module has to guess content
# vocabulary -- unavoidable, because an entity's stats are a bare dictionary and
# something has to be read from it. It matches `PLAYER_DEFAULT_STATS`, so a set
# that declares no `stats` contract behaves exactly as it did before.
STAT_ROLES: Dict[str, str] = {
    "health": "constitution",
    "attack": "strength",
    "defence": "dexterity",
    "evasion": "agility",
    "regeneration": "strength",
    "power": "intelligence",
    "ability_power": "spell_power",
    "resistance": "magic_resist",
}

# The value a stat is assumed to hold when an entity does not carry it. 10 is
# the neutral point of the shipped content: a stat of 10 contributes nothing to
# any curve, so a missing stat is neutral rather than a penalty. An entity whose
# own defaults differ passes them in -- see `PLAYER_DEFAULT_STATS` and
# `NPC_DEFAULT_STATS`, which are per-stat and therefore not one number.
NEUTRAL_STAT_VALUE = 10


def _registry(world: Any):
    return getattr(world, "contract_registry", None)


def declared_stat_roles(world: Any) -> Dict[str, str]:
    """The role-to-stat mapping this content set declares, if it declares one."""
    registry = _registry(world)
    declared = getattr(registry, "stats", None) if registry is not None else None
    if not isinstance(declared, dict):
        return {}
    roles = declared.get("roles")
    if not isinstance(roles, dict):
        return {}
    return {
        str(role): str(stat).strip()
        for role, stat in roles.items()
        if isinstance(stat, str) and stat.strip()
    }


def stat_name(world: Any, role: str) -> str:
    """The stat that fills one role for this content set."""
    resolved = declared_stat_roles(world).get(role)
    if resolved:
        return resolved
    return STAT_ROLES.get(role, "")


def stat_value(stats: Any, stat: str, default: Any = NEUTRAL_STAT_VALUE) -> int:
    """One stat out of a bare dictionary, coerced.

    `default` may be a number or a per-stat map, because entities do not share
    one neutral value: a player's stats neutralise at 10, an NPC's at 8, and an
    NPC's `intelligence` is 5 where its `constitution` is 8. A single blanket
    value would move whichever stat it did not match, and the only symptom would
    be a number nobody had authored.
    """
    if not isinstance(stats, dict) or not stat:
        return _default_for(default, stat)
    value = stats.get(stat, None)
    if value is None:
        return _default_for(default, stat)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _default_for(default, stat)
    return int(value)


def _default_for(default: Any, stat: str) -> int:
    if isinstance(default, dict):
        value = default.get(stat, NEUTRAL_STAT_VALUE)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return NEUTRAL_STAT_VALUE
        return int(value)
    if isinstance(default, bool) or not isinstance(default, (int, float)):
        return NEUTRAL_STAT_VALUE
    return int(default)


def stat_for(world: Any, stats: Any, role: str, default: Any = NEUTRAL_STAT_VALUE) -> int:
    """The value of whichever stat fills one role."""
    return stat_value(stats, stat_name(world, role), default)


def entity_stat_for(entity: Any, role: str, default: Any = NEUTRAL_STAT_VALUE) -> int:
    """One role's value for an entity that carries its own modifiers.

    Reads through `get_effective_stat` so buffs, equipment and set bonuses are
    included -- `stats[stat]` alone is the base value and would quietly ignore
    every modifier in the game.
    """
    stat = stat_name(getattr(entity, "world", None), role)
    if not stat:
        return _default_for(default, stat)
    reader = getattr(entity, "get_effective_stat", None)
    if callable(reader):
        value = reader(stat)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return stat_value(getattr(entity, "stats", None), stat, default)


def stat_short(world: Any, stat: str) -> str:
    """The compact form a status line has room for.

    A content set may declare one; otherwise the stat's own name is shortened,
    which is a guess and is allowed to be an ugly one. `spell_power` shortens to
    nothing useful, which is why a set that cares declares `short`.
    """
    registry = _registry(world)
    declared = getattr(registry, "stats", None) if registry is not None else None
    shorts = declared.get("short") if isinstance(declared, dict) else None
    if isinstance(shorts, dict):
        authored = shorts.get(stat)
        if isinstance(authored, str) and authored.strip():
            return authored.strip()
    return str(stat)[:3].upper()


def declared_stat_order(world: Any) -> Iterable[str]:
    """The stat list a status line shows, as the content set declares it."""
    registry = _registry(world)
    declared = getattr(registry, "stats", None) if registry is not None else None
    order = declared.get("order") if isinstance(declared, dict) else None
    if not isinstance(order, list):
        return ()
    return tuple(str(stat).strip() for stat in order if isinstance(stat, str) and str(stat).strip())


def display_stats(world: Any, fallback: Iterable[str]) -> tuple:
    """The stats to show on a status line, and their labels.

    One entry per stat, in the order the content set declares, so a set that
    renames its stats gets a status line that agrees with it. Falls back to the
    caller's list when the set declares none -- which is how every set behaved
    before this existed.
    """
    declared = tuple(declared_stat_order(world))
    order = declared or tuple(str(stat) for stat in fallback)
    return tuple((stat, stat_short(world, stat)) for stat in order)


def roles_summary(world: Any) -> str:
    """One line naming what fills each role, for a contract listing."""
    roles = {role: stat_name(world, role) for role in STAT_ROLES}
    return ", ".join("%s=%s" % (role, stat) for role, stat in sorted(roles.items()))


def optional_registry_stats(world: Any) -> Optional[Dict[str, Any]]:
    """The raw declared section, for callers that want more than a role."""
    registry = _registry(world)
    declared = getattr(registry, "stats", None) if registry is not None else None
    return declared if isinstance(declared, dict) else None
