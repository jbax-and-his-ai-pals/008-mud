"""Ability resources: the pool an ability spends, as the content set declares it.

The engine has always had exactly one such pool, and it has always been called
mana. That is a content decision wearing engine clothing: a set whose abilities
draw on charge, heat, ammunition or blood has no mana, and its players must
never read the word.

So the pool is resolved from the `resources` contract, and this module is the
one place that decides which declared resource it is:

* the **declared** ability resource is the one whose `kind` is `"ability"`. A set
  declares exactly one; a set that declares two gets the first by id, which is
  arbitrary but deterministic, and the validator's job is to make that case loud
  rather than this module's to guess.
* a set that declares **none** gets `NEUTRAL_ABILITY_RESOURCE` -- deliberately
  named "ability", not "mana", so the fallback never reintroduces the genre word
  into a set that did not ask for it.

The *curve* (how much a pool holds per point of its driving stat, how fast it
regenerates) stays in `engine/config` -- it is a rule, not a name. What content
decides is which stat drives it (`max_stat`, `regeneration_stat`) and what it is
called (`label`, `short`). Those two fields were declared in the contract from
the beginning and read by nothing, which is the pattern this whole initiative
exists to fix: a declaration the engine ignores is worse than no declaration,
because content believes it did something.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from engine.config import (
    ABILITY_POOL_BASE,
    ABILITY_POOL_LEVEL_UP_MULTIPLIER,
    ABILITY_POOL_LEVEL_UP_STAT_DIVISOR,
    ABILITY_POOL_PER_STAT_POINT,
    ABILITY_POOL_REGEN_BASE,
    ABILITY_POOL_REGEN_STAT_DIVISOR,
)

# What a set that declares no ability resource gets. Neutral on purpose: the
# label is a placeholder a content set is expected to replace, and it must not
# hand a sci-fi game the fantasy word for the pool.
NEUTRAL_ABILITY_RESOURCE: Dict[str, Any] = {
    "id": "ability",
    "label": "Ability",
    "short": "ABL",
    "kind": "ability",
    "regenerates": False,
    "max_stat": "",
    "regeneration_stat": "",
}

# The stat a pool is measured against when the declared one is absent.
DEFAULT_POOL_STAT = "intelligence"
DEFAULT_REGEN_STAT = "wisdom"


def _registry(world: Any):
    return getattr(world, "contract_registry", None)


def declared_resources(world: Any) -> Iterable[Dict[str, Any]]:
    registry = _registry(world)
    resources = getattr(registry, "resources", None) if registry is not None else None
    return resources.values() if isinstance(resources, dict) else ()


def ability_resource(world: Any) -> Dict[str, Any]:
    """The declared ability resource, or the neutral fallback."""
    declared = [
        resource for resource in declared_resources(world)
        if isinstance(resource, dict) and str(resource.get("kind", "")) == "ability"
    ]
    if not declared:
        return dict(NEUTRAL_ABILITY_RESOURCE)
    chosen = sorted(declared, key=lambda entry: str(entry.get("id", "")))[0]
    merged = dict(NEUTRAL_ABILITY_RESOURCE)
    merged.update(chosen)
    return merged


def ability_resource_id(world: Any) -> str:
    return str(ability_resource(world).get("id", "") or NEUTRAL_ABILITY_RESOURCE["id"])


def ability_resource_label(world: Any) -> str:
    return str(ability_resource(world).get("label", "") or NEUTRAL_ABILITY_RESOURCE["label"])


def ability_resource_short(world: Any) -> str:
    """The two-or-three letter form a compact status line has room for."""
    resource = ability_resource(world)
    short = str(resource.get("short", "") or "").strip()
    if short:
        return short
    return ability_resource_label(world)[:3].upper()


def label_for(world: Any, resource_id: str) -> str:
    """What a declared resource is called, by id. Used in ability messaging."""
    identifier = str(resource_id or "")
    for resource in declared_resources(world):
        if isinstance(resource, dict) and str(resource.get("id", "")) == identifier:
            return str(resource.get("label", "") or identifier)
    if identifier == ability_resource_id(world):
        return ability_resource_label(world)
    return identifier.replace("_", " ")


def is_ability_resource(world: Any, resource_id: str) -> bool:
    return str(resource_id or "") == ability_resource_id(world)


def _stat_value(stats: Any, stat: str, default: int = 10) -> int:
    if not isinstance(stats, dict) or not stat:
        return default
    value = stats.get(stat, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def pool_for(world: Any, stats: Any) -> int:
    """How much the pool holds, from the stat the contract names.

    Fantasy's numbers are reproduced exactly (`50 + (intelligence - 10) * 5`),
    because `mana` declares `max_stat: "intelligence"`.
    """
    resource = ability_resource(world)
    stat = str(resource.get("max_stat", "") or "") or DEFAULT_POOL_STAT
    return max(1, ABILITY_POOL_BASE + (_stat_value(stats, stat) - 10) * ABILITY_POOL_PER_STAT_POINT)


def pool_stat(world: Any) -> str:
    return str(ability_resource(world).get("max_stat", "") or "") or DEFAULT_POOL_STAT


def regen_stat(world: Any) -> str:
    return str(ability_resource(world).get("regeneration_stat", "") or "") or DEFAULT_REGEN_STAT


def regenerates(world: Any) -> bool:
    """Whether the pool refills on its own between fights."""
    return bool(ability_resource(world).get("regenerates", NEUTRAL_ABILITY_RESOURCE["regenerates"]))


def regen_rate_for(world: Any, stats: Any, base_rate: Optional[float] = None) -> float:
    """The pool's per-second refill, from the stat the contract names."""
    rate = ABILITY_POOL_REGEN_BASE if base_rate is None else float(base_rate)
    return rate * (1 + _stat_value(stats, regen_stat(world)) / ABILITY_POOL_REGEN_STAT_DIVISOR)


def pool_on_level_up(world: Any, current_max: int, stats: Any) -> int:
    """How much more the pool holds after a level, from the contract's stat."""
    stat = _stat_value(stats, pool_stat(world))
    return int(
        int(current_max) * (ABILITY_POOL_LEVEL_UP_MULTIPLIER - 1)
        + stat / ABILITY_POOL_LEVEL_UP_STAT_DIVISOR
    )
