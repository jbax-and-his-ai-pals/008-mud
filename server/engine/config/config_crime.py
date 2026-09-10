# engine/config/config_crime.py
"""
Configuration for theft, witness detection, notoriety, and jail.
"""

# --- Witness Detection ---
# An NPC witness's "perception" is a derived difficulty, not a tracked
# skill (NPCs don't level skills the way players do) -- level and a flat
# base scale it, and guards get a flat bonus ("guards are better at
# noticing" per the design, not a new faction).
NPC_BASE_PERCEPTION = 20
NPC_PERCEPTION_PER_LEVEL = 3
GUARD_PERCEPTION_BONUS = 20

# --- Stealth XP ---
THEFT_STEALTH_XP_SUCCESS = 15
THEFT_STEALTH_XP_CAUGHT = 3

# --- Crime Resolution ---
# Notoriety (player.reputation["town_guard"]) drops per gold-value stolen
# when caught, separate from and unrelated to the combat-faction
# reputation system.
CRIME_NOTORIETY_PER_THEFT_VALUE = 0.5
# Fine vs. jail is decided from this theft's value, the player's running
# total stolen value, and their town_guard reputation -- first/small
# offenses lean fine, repeat/high-value/low-reputation escalates to jail.
CRIME_JAIL_VALUE_THRESHOLD = 100
CRIME_JAIL_CUMULATIVE_THRESHOLD = 250
CRIME_JAIL_REPUTATION_THRESHOLD = -30
CRIME_FINE_RATE = 2.0
CRIME_FINE_MINIMUM = 10

# --- Jail Sentencing ---
JAIL_BASE_SENTENCE_SECONDS = 60.0
JAIL_SENTENCE_PER_THEFT_VALUE = 0.5
# A severe-enough escape failure alerts the guards and extends the
# sentence; an ordinary failure is a free, safe retry. Mirrors
# TRAP_DISARM_TRIGGER_MARGIN_THRESHOLD's existing pattern.
JAIL_ESCAPE_ALERT_MARGIN_THRESHOLD = 15
JAIL_ESCAPE_ALERT_PENALTY_SECONDS = 45.0

# --- Concealed Escape Pick ---
# A bottleneck of two independent skill floors, not a new stat -- see
# docs/design/place_making_and_town_security.md.
CONCEALED_PICK_STEALTH_FLOOR = 20
CONCEALED_PICK_LOCKPICKING_FLOOR = 20
EMERGENCY_LOCKPICK_DURABILITY = 4

# --- Jail Cell Search ---
JAIL_SEARCH_SUCCESS_CHANCE = 0.15
JAIL_SEARCH_REWARD_GOLD_MIN = 1
JAIL_SEARCH_REWARD_GOLD_MAX = 5
