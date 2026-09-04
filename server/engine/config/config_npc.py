# engine/config/config_npc.py
"""
Configuration for NPCs, including defaults, stats, combat, and behavior.
"""

# --- NPC Defaults & Base Values ---
NPC_DEFAULT_BEHAVIOR = "stationary"
NPC_DEFAULT_MAX_MANA = 0
NPC_BASE_HEALTH_REGEN_RATE = 1.0
NPC_BASE_MANA_REGEN_RATE = 1.0
NPC_DEFAULT_WANDER_CHANCE = 0.3
NPC_DEFAULT_MOVE_COOLDOWN = 10
NPC_DEFAULT_AGGRESSION = 0.0
NPC_DEFAULT_WANDER = 0.3
NPC_DEFAULT_FLEE_THRESHOLD = 0.2
NPC_DEFAULT_RESPAWN_COOLDOWN = 600
NAMED_NPC_RESPAWN_COOLDOWN = 60
NPC_MAX_COMBAT_MESSAGES = 5
NPC_BEHAVIOR_TYPES = ["stationary", "wanderer", "patrol", "follower", "scheduled", "aggressive", "minion"]

# --- NPC Health & Mana ---
NPC_BASE_HEALTH = 30
NPC_CON_HEALTH_MULTIPLIER = 1.5
NPC_LEVEL_HEALTH_BASE_INCREASE = 3
NPC_LEVEL_CON_HEALTH_MULTIPLIER = 0.3
NPC_MANA_LEVEL_UP_MULTIPLIER = 1.10
NPC_MANA_LEVEL_UP_INT_DIVISOR = 3
NPC_MANA_REGEN_WISDOM_DIVISOR = 22

# --- NPC Stats & Leveling ---
NPC_DEFAULT_STATS = {
    "strength": 8, "dexterity": 8, "intelligence": 5,
    "wisdom": 5, "constitution": 8, "agility": 8,
    "spell_power": 0, "magic_resist": 0,
    "resistances": {} # NEW: Add default resistances dictionary
}
NPC_BASE_XP_TO_LEVEL = 150
NPC_XP_TO_LEVEL_MULTIPLIER = 1.6
NPC_LEVEL_UP_STAT_INCREASE = 1
NPC_LEVEL_UP_HEALTH_HEAL_PERCENT = 0.5

# --- NPC Combat ---
NPC_BASE_HIT_CHANCE = 0.80
NPC_ATTACK_DAMAGE_VARIATION_RANGE = (-1, 1)
NPC_DEFAULT_COMBAT_COOLDOWN = 3.0
NPC_DEFAULT_ATTACK_COOLDOWN = 3.0
NPC_DEFAULT_SPELL_CAST_CHANCE = 0.0
NPC_BASE_ATTACK_POWER = 3
NPC_BASE_DEFENSE = 2

# --- NPC Behavior ---
NPC_LOW_MANA_RETREAT_THRESHOLD = 0.20
NPC_HEALTH_DESC_THRESHOLDS = (0.25, 0.50, 0.75) # severely injured, wounded, minor injuries
NPC_HEALER_HEAL_THRESHOLD = 0.75

# --- NPC Naming ---
VILLAGER_FIRST_NAMES_MALE = [
    "Alex", "Avery", "Cameron", "Casey", "Drew", "Elliot", "Harper", "Jamie", "Jordan", "Lee",
    "Logan", "Morgan", "Parker", "Quinn", "Reese", "Robin", "Rowan", "Sage", "Taylor", "Terry", "Wes", "Zane"
]
VILLAGER_FIRST_NAMES_FEMALE = [
    "Alex", "Avery", "Cameron", "Casey", "Drew", "Emery", "Harper", "Jamie", "Jordan", "Kai",
    "Logan", "Morgan", "Parker", "Quinn", "Reese", "Robin", "Rowan", "Sage", "Taylor", "Terry", "Wren", "Zoe"
]
VILLAGER_LAST_NAMES = [
    "Bailey", "Bennett", "Brooks", "Carter", "Chen", "Davis", "Ellis", "Garcia", "Hughes", "Kim",
    "Lee", "Martin", "Miller", "Morgan", "Nguyen", "Parker", "Patel", "Reed", "Rivera", "Shaw", "Taylor", "Walker", "Young", "Zhang"
]

# --- NPC Flavor Text ---
NPC_DOT_FLAVOR_MESSAGES = [
    "{npc_name} winces in pain from the {effect_name}.",
    "The {effect_name} visibly weakens {npc_name}.",
    "{npc_name} stumbles as the {effect_name} takes its toll.",
    "A flicker of pain crosses {npc_name}'s face due to the {effect_name}.",
    "{npc_name} lets out a pained grunt from the effects of the {effect_name}."
]
