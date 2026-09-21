# engine/config/config_combat.py
"""
Configuration for shared combat mechanics, damage calculations, and status effects.
Loads dynamic elemental data from JSON.
"""
import json
import os
from typing import Any, Optional

# --- Shared Combat Mechanics ---
MIN_HIT_CHANCE = 0.05
MAX_HIT_CHANCE = 0.95
MIN_XP_GAIN = 1
MIN_ATTACK_COOLDOWN = 0.5
HIT_CHANCE_AGILITY_FACTOR = 0.02
MINIMUM_DAMAGE_TAKEN = 1

# --- Level Difference Modifiers ---
LEVEL_DIFF_COMBAT_MODIFIERS = {
    "purple": (0.70, 0.60, 2.50),
    "red":    (0.85, 0.75, 1.75),
    "orange": (0.95, 0.90, 1.25),
    "yellow": (1.00, 1.00, 1.00),
    "blue":   (1.05, 1.10, 0.80),
    "green":  (1.15, 1.25, 0.50),
    "gray":   (1.25, 1.40, 0.20),
}

# --- Weapon damage type vs. armor material ---
# A physical-damage-only tradeoff (separate from the elemental system loaded
# by configure_combat_elements): what a weapon's edge geometry does against
# what the defender's body armor is made of. Slashing is what cloth and
# leather lose to but what mail and plate were built to defeat; piercing
# thrusts are the historically documented answer to mail (a point slips
# through or between rings) but plate's curved rigid surface deflects most
# of them; crushing/blunt force transmits through rigid armor as concussion
# regardless of penetration, which is why maces and war-hammers were the
# dedicated plate-answer, at the cost of being the least specialised choice
# against soft, unarmored targets. Hardcoded like LEVEL_DIFF_COMBAT_MODIFIERS
# above rather than content-loaded: this is physical combat math, not
# per-content-set theming, and every field defaults safely (no body armor,
# or a content set that never sets these properties at all, multiplies by
# 1.0 -- unarmored/undefined fights are unaffected).
WEAPON_DAMAGE_TYPES = ["slashing", "piercing", "crushing"]
ARMOR_MATERIALS = ["cloth", "leather", "chain", "plate"]
DEFAULT_WEAPON_DAMAGE_TYPE = "slashing"
UNARMED_WEAPON_DAMAGE_TYPE = "crushing"
WEAPON_VS_ARMOR_MULTIPLIERS = {
    "slashing": {"cloth": 1.30, "leather": 1.15, "chain": 0.85, "plate": 0.70},
    "piercing": {"cloth": 1.00, "leather": 1.10, "chain": 1.25, "plate": 0.80},
    "crushing": {"cloth": 0.95, "leather": 1.00, "chain": 1.10, "plate": 1.25},
}

# --- Experience Point Calculation ---
XP_GAIN_HEALTH_DIVISOR = 5
XP_GAIN_LEVEL_MULTIPLIER = 5
SPELL_XP_GAIN_HEALTH_DIVISOR = 4
SPELL_XP_GAIN_LEVEL_MULTIPLIER = 6

# --- Magic & Spell Effects ---
SPELL_DAMAGE_VARIATION_FACTOR = 0.1
MINIMUM_SPELL_EFFECT_VALUE = 1
SPELL_EFFECT_TYPES = ["damage", "heal", "buff", "debuff", "summon", "cleanse", "remove_curse", "life_tap"]

# --- Status Effect Settings ---
EFFECT_DEFAULT_TICK_INTERVAL = 3.0
EFFECT_POISON_DAMAGE_TYPE = "poison"

# --- DYNAMIC ELEMENTAL LOADING ---
_DEFAULT_ELEMENTAL_DATA = {
    "valid_damage_types": ["physical", "magical"],
    "default_damage_type": "magical",
    "elemental_opposites": {},
    "flavor_text": {"default": {"weakness": "Hits weak!", "resistance": "Resisted.", "strong_resistance": "Strongly resisted."}},
    "hazards": {},
}

VALID_DAMAGE_TYPES = list(_DEFAULT_ELEMENTAL_DATA["valid_damage_types"])
# Held in a mutable cell, not a string: `configure_combat_elements` runs when a
# world is constructed, which is *after* every module has imported this, so a
# plain module-level string would freeze the default at the built-in value and
# silently ignore the set's own. Read it through `spell_default_damage_type()`.
_SPELL_DEFAULT = [_DEFAULT_ELEMENTAL_DATA["default_damage_type"]]
ELEMENTAL_OPPOSITES: dict = {}
DAMAGE_TYPE_FLAVOR_TEXT: dict = dict(_DEFAULT_ELEMENTAL_DATA["flavor_text"])

# One record per hazard, keyed by the id a room names. A hazard used to be three
# expressions of the same fact: `hazards.mapping` said which damage channel it
# was, `hazards.flavor` said what it read like *keyed by that channel* (so two
# hazards sharing a channel shared a sentence), and each room restated its
# damage and tick interval as untyped properties. Now the declaration carries all
# of it, and a room names the hazard. A room may still override the numbers, for
# the authored case where this instance of a hazard is worse.
#
# Loaded from a content set's `combat/elements.json` through
# `configure_combat_elements`; read through `engine/world/environment.py`.
HAZARD_TYPES: dict = {}

# What a hazard deals and how often, when its own record does not say. These were
# literals inside `room.apply_hazards`, which meant every content set inherited a
# number no author had agreed to; named here so they are visibly engine defaults.
HAZARD_DEFAULT_DAMAGE = 5
HAZARD_DEFAULT_TICK_INTERVAL = 3.0


def spell_default_damage_type() -> str:
    """The damage channel a spell with no `damage_type` of its own deals."""
    return _SPELL_DEFAULT[0]


def _normalize_hazard(entry: Any) -> Optional[dict]:
    """One declared hazard as the engine reads it, or None when it is unreadable.

    The validator reports a malformed record with its file and field; the loader
    refuses to half-load it rather than guessing a channel or a sentence. A hazard
    that does nothing is a smaller failure than one that damages a player through
    a channel its author never chose, in prose its author never wrote.
    """
    if not isinstance(entry, dict):
        return None
    channel = str(entry.get("channel", "") or "").strip()
    flavor = str(entry.get("flavor", "") or "").strip()
    if not channel or not flavor:
        return None
    damage = entry.get("damage", HAZARD_DEFAULT_DAMAGE)
    if isinstance(damage, bool) or not isinstance(damage, (int, float)):
        damage = HAZARD_DEFAULT_DAMAGE
    interval = entry.get("tick_interval", HAZARD_DEFAULT_TICK_INTERVAL)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        interval = HAZARD_DEFAULT_TICK_INTERVAL
    return {
        "channel": channel,
        "flavor": flavor,
        "damage": int(damage),
        "tick_interval": float(interval),
    }


def configure_combat_elements(content_root: str) -> None:
    """Load elemental definitions from the selected content package."""
    path = os.path.join(content_root, "combat", "elements.json")
    data = _DEFAULT_ELEMENTAL_DATA
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as file:
            parsed = json.load(file)
        if isinstance(parsed, dict):
            data = parsed
    VALID_DAMAGE_TYPES[:] = list(data.get("valid_damage_types", _DEFAULT_ELEMENTAL_DATA["valid_damage_types"]))
    _SPELL_DEFAULT[0] = str(data.get("default_damage_type", _DEFAULT_ELEMENTAL_DATA["default_damage_type"]))
    ELEMENTAL_OPPOSITES.clear(); ELEMENTAL_OPPOSITES.update(data.get("elemental_opposites", {}))
    DAMAGE_TYPE_FLAVOR_TEXT.clear(); DAMAGE_TYPE_FLAVOR_TEXT.update(data.get("flavor_text", _DEFAULT_ELEMENTAL_DATA["flavor_text"]))
    declared = data.get("hazards", {})
    HAZARD_TYPES.clear()
    if isinstance(declared, dict):
        for hazard_id, entry in declared.items():
            record = _normalize_hazard(entry)
            if record is not None and str(hazard_id).strip():
                HAZARD_TYPES[str(hazard_id).strip()] = record
