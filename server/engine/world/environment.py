# engine/world/environment.py
"""What a room's environment does to whoever is standing in it.

**One declaration, resolved once.** "This room is dangerous" used to be three
expressions of the same fact, in three places with three owners:

* `combat/elements.json`'s `hazards.mapping` said which damage channel a hazard
  *was* (`extreme_heat -> fire`);
* the same file's `hazards.flavor` said what it read like, **keyed by that
  channel** -- so two hazards sharing a channel shared one sentence, and a
  hazard's own name never reached a player;
* each room restated its damage and tick interval as untyped properties
  (`hazard_damage`, `hazard_tick_interval`) next to the `hazard_type` that named
  the hazard in the first place.

Now a hazard is one record in the content set's own words -- channel, prose, base
damage, tick interval -- and a room names it. A room may still override the
numbers, because two instances of the same hazard can honestly differ
(`fantasy_frontier` runs `extreme_heat` hotter in one room than another); that is
an override of a declared value rather than a second declaration of it.

**Where the pieces live.** The declaration is loaded by
`config.configure_combat_elements` into `HAZARD_TYPES`; this module composes it
with the room, the weather and the target. `Room.apply_hazards` delegates here so
there is one implementation rather than a new one shadowing an old one, which is
what the track roadmap asked for: land the reader, let the owner of `world/**`
delete the old path.

**Mitigation is not decided here.** Damage goes through `entity.take_damage`,
which already resolves the content set's `resistance` stat and the target's
per-channel `resistances` from armour. A hazard that ignored that would be a
second damage path with its own rules.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from engine.config.config_combat import (
    HAZARD_DEFAULT_DAMAGE,
    HAZARD_DEFAULT_TICK_INTERVAL,
    HAZARD_TYPES,
)


def declared(hazard_id: str) -> Optional[Dict[str, Any]]:
    """The record a content set declared for one hazard, or None.

    None means "this hazard is not declared here", and every caller treats it as
    inert. A room naming an undeclared hazard is a content error the validator
    reports by file and field; making it inert at runtime as well keeps a world
    with one bad room playable instead of hostile in a way nobody authored.
    """
    if not hazard_id:
        return None
    record = HAZARD_TYPES.get(str(hazard_id).strip())
    return dict(record) if isinstance(record, dict) else None


def hazard_in(world: Any, room: Any) -> Optional[Dict[str, Any]]:
    """The hazard this room presents, with the room's own numbers applied.

    Returns `{id, channel, flavor, damage, tick_interval, multipliers}` or None.
    """
    properties = getattr(room, "properties", None)
    if not isinstance(properties, dict):
        return None
    hazard_id = properties.get("hazard_type")
    if not isinstance(hazard_id, str) or not hazard_id.strip():
        return None
    record = declared(hazard_id)
    if record is None:
        return None
    record["id"] = hazard_id.strip()
    record["damage"] = _override(
        properties.get("hazard_damage"), record.get("damage", HAZARD_DEFAULT_DAMAGE), int
    )
    record["tick_interval"] = _override(
        properties.get("hazard_tick_interval"),
        record.get("tick_interval", HAZARD_DEFAULT_TICK_INTERVAL),
        float,
    )
    multipliers = properties.get("weather_hazard_multipliers")
    record["multipliers"] = multipliers if isinstance(multipliers, dict) else {}
    return record


def weather_multiplier(world: Any, hazard: Dict[str, Any], region: Any = None, room: Any = None) -> float:
    """What the weather does to this hazard's damage where it is being applied.

    Weather is read through the weather manager, which is the only thing that
    knows what the weather *is* here (region climate, season, a room's own
    override). A room that names no multipliers, a region that is not the one the
    target is standing in, or a world with no weather at all gets 1.0 -- an absent
    weather system must not change hazard damage.
    """
    multipliers = hazard.get("multipliers") or {}
    if not isinstance(multipliers, dict) or not multipliers:
        return 1.0
    weather_manager = getattr(getattr(world, "game", None), "weather_manager", None)
    if weather_manager is None or world is None or region is None:
        return 1.0
    weather = weather_manager.effective_weather(region, room)
    factor = multipliers.get(weather, 1)
    if isinstance(factor, (int, float)) and not isinstance(factor, bool) and factor > 0:
        return float(factor)
    return 1.0


def damage_of(world: Any, room: Any, hazard: Dict[str, Any], region: Any = None) -> int:
    """The damage one tick deals, after weather, never below 1."""
    base = hazard.get("damage", HAZARD_DEFAULT_DAMAGE)
    scaled = float(base) * weather_multiplier(world, hazard, region, room)
    return max(1, int(round(scaled)))


def apply(
    world: Any,
    room: Any,
    entity: Any,
    now: float,
    last_ticks: Optional[Dict[str, float]] = None,
) -> Optional[str]:
    """Damage `entity` for standing in `room`, and return what it reads like.

    `None` means nothing happened this call: no hazard, a dead or absent entity,
    a tick that is not due yet, or damage the target shrugged off entirely.
    `last_ticks` is the per-room, per-entity tick bookkeeping, owned by the room
    and passed in so this stays a function of its arguments.
    """
    if entity is None or not getattr(entity, "is_alive", True):
        return None
    hazard = hazard_in(world, room)
    if hazard is None:
        return None

    interval = hazard.get("tick_interval", HAZARD_DEFAULT_TICK_INTERVAL)
    entity_id = getattr(entity, "obj_id", None)
    if entity_id and isinstance(last_ticks, dict):
        last = last_ticks.get(entity_id, 0.0)
        if now - last < interval:
            return None
        last_ticks[entity_id] = now

    # The weather that applies is the weather where the *target* is standing, not
    # wherever the room object happens to live: rooms carry no region of their own.
    region = None
    if world is not None:
        region = world.get_region(str(getattr(entity, "current_region_id", "") or ""))

    taken = entity.take_damage(damage_of(world, room, hazard, region), hazard["channel"])
    if taken <= 0:
        return None
    return prose(hazard, taken)


def prose(hazard: Dict[str, Any], taken: int) -> str:
    """The sentence a player reads, in the content set's own words.

    The number is appended here rather than written by content: the amount is the
    engine's arithmetic, and a set that hardcoded it in prose would be wrong the
    first time a weather multiplier or a resistance changed it.
    """
    return "%s (-%d HP)" % (hazard.get("flavor", ""), taken)


def _override(value: Any, default: Any, cast) -> Any:
    """A room's own number when it is a usable one, else the declaration's."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if value <= 0:
        return default
    return cast(value)
