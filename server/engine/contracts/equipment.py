"""What the engine asks about equipment, answered by the contracts.

The combat path used to read raw template properties straight off an item:
`get_property("damage")` for a weapon, `get_property("defense")` and
`get_property("armor_material")` for armour, the spell's own `mana_cost` and
`cooldown` for a cast. Those properties still work — that is what makes the
migration possible one item at a time — but content may now declare an
**attack profile**, a **defense profile**, or an **ability**, and the profile
wins.

The rule everywhere in this module is the same:

    contract first, authored property second, engine default last

so a content set can move an item onto a contract without a flag day, and an
item nobody has migrated behaves exactly as it did.

Nothing here branches on a genre word. A weapon resolves through the profile its
template names; a sci-fi content set names its own profiles and gets the same
path. `toolkit/genre_coupling_audit.py` measures what is left.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from engine.config.config_combat import (
    DEFAULT_WEAPON_DAMAGE_TYPE,
    UNARMED_WEAPON_DAMAGE_TYPE,
)
from engine.contracts.registry import registry_for
from engine.contracts.resources import ability_resource_id, is_ability_resource


def _template_of(world: Any, item: Any) -> Dict[str, Any]:
    """The template an item instance came from, when the world can supply it."""
    if item is None:
        return {}
    template_id = str(getattr(item, "obj_id", "") or "")
    templates = getattr(world, "item_templates", None)
    if isinstance(templates, dict):
        template = templates.get(template_id)
        if isinstance(template, dict):
            return template
    return {}


def _item_property(item: Any, name: str, default: Any = None) -> Any:
    getter = getattr(item, "get_property", None)
    if callable(getter):
        return getter(name, default)
    return default


def profile_for(world: Any, item: Any, key: str) -> Dict[str, Any]:
    """The contract profile an item resolves to for `key`.

    A template may name one directly (`attack_profile`, `defense_profile`), or
    its family may stand in for the whole family of items. Template wins.
    """
    registry = registry_for(world)
    if registry is None:
        return {}
    template = _template_of(world, item)
    named = str(template.get(key, "") or "")
    if not named:
        family_id = str(template.get("item_family", "") or "")
        family = registry.family(family_id) if family_id else None
        if family:
            named = str(family.get(key, "") or "")
    if not named:
        return {}
    bucket = {
        "attack_profile": registry.attack_profiles,
        "defense_profile": registry.defense_profiles,
    }.get(key, {})
    return bucket.get(named, {}) or {}


# -- weapons ------------------------------------------------------------------

def weapon_damage(world: Any, item: Any) -> int:
    """Damage this weapon adds, contract first."""
    profile = profile_for(world, item, "attack_profile")
    if profile and isinstance(profile.get("damage"), (int, float)):
        return int(profile["damage"])
    value = _item_property(item, "damage", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def weapon_damage_type(world: Any, item: Any) -> str:
    """The material-interaction type (slashing/piercing/crushing) of a weapon.

    This is the type compared against a defender's armour material, not the
    damage *channel* — `attack_profiles[].damage_type` is that one, and it feeds
    the resistance maths.
    """
    profile = profile_for(world, item, "attack_profile")
    authored = str(profile.get("weapon_damage_type", "") or "")
    if authored:
        return authored
    if item is None:
        return UNARMED_WEAPON_DAMAGE_TYPE
    value = str(_item_property(item, "weapon_damage_type", "") or "")
    return value or DEFAULT_WEAPON_DAMAGE_TYPE


def damage_channel(world: Any, item: Any) -> str:
    """The damage *type* a weapon deals (physical, fire, …), contract first."""
    profile = profile_for(world, item, "attack_profile")
    authored = str(profile.get("damage_type", "") or "")
    if authored:
        return authored
    value = str(_item_property(item, "damage_type", "") or "")
    return value or "physical"


# -- armour -------------------------------------------------------------------

def armor_defense(world: Any, item: Any) -> int:
    profile = profile_for(world, item, "defense_profile")
    if profile and isinstance(profile.get("defense"), (int, float)):
        return int(profile["defense"])
    value = _item_property(item, "defense", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def armor_material(world: Any, item: Any) -> str:
    profile = profile_for(world, item, "defense_profile")
    authored = str(profile.get("material", "") or "")
    if authored:
        return authored
    return str(_item_property(item, "armor_material", "") or "")


def armor_resistances(world: Any, item: Any) -> Dict[str, float]:
    """Per-damage-type resistance percentages this item grants.

    The authored property is the base; a profile overrides the keys it declares,
    so a contract can retune one resistance without restating the rest.
    """
    merged: Dict[str, float] = {}
    raw = _item_property(item, "resistances", {})
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[str(key)] = float(value)
    profile = profile_for(world, item, "defense_profile")
    declared = profile.get("resistances")
    if isinstance(declared, dict):
        for key, value in declared.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[str(key)] = float(value)
    return merged


# -- abilities ----------------------------------------------------------------

def ability_for_spell(world: Any, spell_or_id: Any) -> Dict[str, Any]:
    """The declared ability behind a spell, or {} when content declares none."""
    registry = registry_for(world)
    if registry is None:
        return {}
    spell_id = getattr(spell_or_id, "spell_id", spell_or_id)
    return registry.ability(str(spell_id or "")) or {}


def ability_numbers(world: Any, spell: Any) -> Dict[str, Any]:
    """Cost, cooldown, targeting and level for a spell, contract first.

    Returned as a dict rather than mutating the `Spell` because a `Spell` is a
    shared content object and a cast is a per-player event; the caller applies
    these to the caster, not to the definition.

    The cost is charged against the content set's **ability resource** -- the
    resource its `resources` contract declares with `kind: "ability"`, whatever
    that resource is called. `mana_cost` keeps its historic name because the
    player runtime's pool does; what changed is that the pool is no longer
    assumed to be mana.
    """
    numbers = {
        "mana_cost": int(getattr(spell, "mana_cost", 0) or 0),
        "cooldown": float(getattr(spell, "cooldown", 0.0) or 0.0),
        "target_type": str(getattr(spell, "target_type", "enemy") or "enemy"),
        "level_required": int(getattr(spell, "level_required", 1) or 1),
        "resource": ability_resource_id(world),
    }
    ability = ability_for_spell(world, spell)
    if not ability:
        return numbers

    cost = ability.get("cost")
    if isinstance(cost, dict):
        resource = str(cost.get("resource", "") or "")
        amount = cost.get("amount")
        # A cost in any other declared resource (health, currency, a material)
        # is legal content but is not this pool's business; charging it here
        # would silently spend the wrong thing.
        if is_ability_resource(world, resource) and isinstance(amount, (int, float)) and not isinstance(amount, bool):
            numbers["mana_cost"] = int(amount)
    if isinstance(ability.get("cooldown"), (int, float)) and not isinstance(ability.get("cooldown"), bool):
        numbers["cooldown"] = float(ability["cooldown"])
    if str(ability.get("target_type", "") or ""):
        numbers["target_type"] = str(ability["target_type"])
    if isinstance(ability.get("level_required"), int) and not isinstance(ability.get("level_required"), bool):
        numbers["level_required"] = int(ability["level_required"])
    return numbers
