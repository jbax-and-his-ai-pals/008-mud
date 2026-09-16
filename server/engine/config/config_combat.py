# engine/config/config_combat.py
"""
Configuration for shared combat mechanics, damage calculations, and status effects.
Loads dynamic elemental data from JSON.
"""
import json
import os

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
    "hazards": {"mapping": {}, "flavor": {}},
}

VALID_DAMAGE_TYPES = list(_DEFAULT_ELEMENTAL_DATA["valid_damage_types"])
SPELL_DEFAULT_DAMAGE_TYPE = _DEFAULT_ELEMENTAL_DATA["default_damage_type"]
ELEMENTAL_OPPOSITES: dict = {}
DAMAGE_TYPE_FLAVOR_TEXT: dict = dict(_DEFAULT_ELEMENTAL_DATA["flavor_text"])
HAZARD_TYPE_MAP: dict = {}
HAZARD_FLAVOR_TEXT: dict = {}


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
    ELEMENTAL_OPPOSITES.clear(); ELEMENTAL_OPPOSITES.update(data.get("elemental_opposites", {}))
    DAMAGE_TYPE_FLAVOR_TEXT.clear(); DAMAGE_TYPE_FLAVOR_TEXT.update(data.get("flavor_text", _DEFAULT_ELEMENTAL_DATA["flavor_text"]))
    hazards = data.get("hazards", {})
    HAZARD_TYPE_MAP.clear(); HAZARD_TYPE_MAP.update(hazards.get("mapping", {}))
    HAZARD_FLAVOR_TEXT.clear(); HAZARD_FLAVOR_TEXT.update(hazards.get("flavor", {}))
