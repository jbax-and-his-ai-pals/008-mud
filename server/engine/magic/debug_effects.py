# engine/magic/debug_effects.py
"""
A registry of pre-defined status effects for easy application via debug commands.
"""

DEBUG_EFFECTS = {
    # --- Harmful ---
    "debug_poison": {
        "type": "dot",
        "name": "Debug Poison",
        "base_duration": 30.0,
        "damage_per_tick": 5,
        "tick_interval": 3.0,
        "damage_type": "poison"
    },
    "debug_bleed": {
        "type": "dot",
        "name": "Bleeding",
        "base_duration": 15.0,
        "damage_per_tick": 3,
        "tick_interval": 1.0,
        "damage_type": "physical",
        "tags": ["physical", "bleed"]
    },
    "debug_weaken": {
        "type": "stat_mod",
        "name": "Weaken",
        "base_duration": 20.0,
        "modifiers": {"strength": -5}
    },
    "debug_stun": {
        "type": "control",
        "name": "Stun",
        "base_duration": 9.0,
        # No other properties needed, the name "Stun" is the key
    },
    "debug_silence": {
        "type": "debuff",
        "name": "Silenced",
        "base_duration": 15.0,
        "tags": ["curse", "magic"]
    },
    "debug_blind": {
        "type": "debuff",
        "name": "Blind",
        "base_duration": 15.0,
        "tags": ["physical"]
    },

    # --- Beneficial ---
    "debug_regen": {
        "type": "hot",
        "name": "Regeneration",
        "base_duration": 30.0,
        "heal_per_tick": 5,
        "tick_interval": 3.0,
    },
    "debug_haste": {
        "type": "stat_mod",
        "name": "Haste",
        "base_duration": 20.0,
        "modifiers": {"agility": 10}
    },
    "debug_vampirism": {
        "type": "buff",
        "name": "Vampirism",
        "base_duration": 30.0,
        "description": "Heals for 50% of damage dealt."
    }
}