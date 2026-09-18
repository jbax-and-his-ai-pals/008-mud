"""Versioned content contracts (ROADMAP P9).

The engine kernel should not know the words "gem", "mana", "sword" or "spell".
Content declares what a thing is — an item family, a generation profile, a
resource, an ability, an effect packet — and the contract says what the engine
does with it. `docs/design/cross_theme_engine_contracts.md` is the design;
`toolkit/genre_coupling_audit.py` measures how much of the engine still branches
on genre vocabulary instead.

    from engine.contracts import ContractRegistry

    registry = ContractRegistry.load(world.content_root)
    family = registry.family("collectible_stone")      # {'item_class': 'Gem', ...}
    tiers = registry.tiers("faceted_stone", "size_tiers")

`engine.contracts.resources` is the one place that decides which declared
resource is the pool an ability spends, so a content set whose abilities draw on
charge rather than mana is not a special case anywhere else.
"""

from engine.contracts.registry import (
    CONTRACTS_DIRECTORY,
    CONTRACTS_FILENAME,
    CONTRACT_SCHEMAS,
    DEFAULT_GENERATION_PROFILE,
    SCHEMA_VERSION,
    ContractRegistry,
    generation_profile_for_template,
    item_class_for_template,
    registry_for,
)
from engine.contracts.equipment import (
    ability_for_spell,
    ability_numbers,
    armor_defense,
    armor_material,
    armor_resistances,
    damage_channel,
    profile_for,
    weapon_damage,
    weapon_damage_type,
)
from engine.contracts.schema import SchemaError, validate_fields, validate_list
from engine.contracts.resources import (
    NEUTRAL_ABILITY_RESOURCE,
    ability_resource,
    ability_resource_id,
    ability_resource_label,
    ability_resource_short,
    is_ability_resource,
    label_for as resource_label,
    pool_for,
    pool_on_level_up,
    regen_rate_for,
)

__all__ = [
    "CONTRACTS_DIRECTORY",
    "CONTRACTS_FILENAME",
    "CONTRACT_SCHEMAS",
    "DEFAULT_GENERATION_PROFILE",
    "NEUTRAL_ABILITY_RESOURCE",
    "SCHEMA_VERSION",
    "ContractRegistry",
    "ability_for_spell",
    "ability_numbers",
    "ability_resource",
    "ability_resource_id",
    "ability_resource_label",
    "ability_resource_short",
    "armor_defense",
    "armor_material",
    "armor_resistances",
    "damage_channel",
    "is_ability_resource",
    "pool_for",
    "pool_on_level_up",
    "profile_for",
    "regen_rate_for",
    "resource_label",
    "weapon_damage",
    "weapon_damage_type",
    "generation_profile_for_template",
    "item_class_for_template",
    "registry_for",
    "SchemaError",
    "validate_fields",
    "validate_list",
]
