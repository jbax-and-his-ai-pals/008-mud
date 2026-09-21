# engine/config/config_world.py
"""
Configuration for the game world, including simulation, spawning, and factions.
"""

# --- World Settings ---
WORLD_UPDATE_INTERVAL = 0.5
DYNAMIC_REGION_DEFAULT_NUM_ROOMS = 20

# --- Monster Spawner Settings ---
SPAWN_INTERVAL_SECONDS = 5.0
SPAWN_CHANCE_PER_TICK = 1.0
SPAWN_ROOMS_PER_MONSTER = 5
SPAWN_MIN_MONSTERS_PER_REGION = 0
SPAWN_MAX_MONSTERS_PER_REGION_CAP = 3
SPAWN_DEBUG = False

# --- Faction Settings ---
FACTIONS = ["player", "friendly", "neutral", "hostile", "player_minion"]

# A disposition is the *coarse* question ("is this thing on the player's side?"),
# and it is what a content set declares when it wants its own names for enemies
# or allies. `engine/world/factions.py` is the one place that reads these.
FACTION_DISPOSITIONS = ("hostile", "friendly", "neutral", "player")

# Which disposition each engine faction has by default. `player_minion` is
# `player` on purpose: a summoned thing fights for you, which is why it is
# excluded from conversation by `is_summoned` rather than by its faction.
FACTION_DEFAULT_DISPOSITIONS = {
    "player": "player",
    "player_minion": "player",
    "friendly": "friendly",
    "neutral": "neutral",
    "hostile": "hostile",
}

# How a disposition expands into an attitude row. A faction with its own name
# gets its disposition's row, so an author declaring "these are my enemies"
# never has to write a matrix; `factions.py` then zeroes the row between
# factions that share a disposition (two hostile kinds ignore each other, as
# the built-in `hostile` row ignores itself).
FACTION_DISPOSITION_ROWS = {
    "player": {
        "player": 100, "player_minion": 100, "friendly": 100,
        "neutral": 0, "hostile": -100
    },
    "friendly": {
        "player": 100, "player_minion": 100, "friendly": 100,
        "neutral": 0, "hostile": -100
    },
    "neutral": {
        "player": 0, "player_minion": 0, "friendly": 0,
        "neutral": 0, "hostile": 0
    },
    "hostile": {
        "player": -100, "player_minion": -100, "friendly": -100,
        "neutral": -100, "hostile": 0
    },
}

# The engine's five rows, unchanged: derived from the table above so there is
# one place holding the numbers and `npcs/combat.py` keeps its flat lookup.
FACTION_RELATIONSHIP_MATRIX = {
    faction: dict(FACTION_DISPOSITION_ROWS[FACTION_DEFAULT_DISPOSITIONS[faction]])
    for faction in FACTIONS
}

# --- Reputation Thresholds ---
REP_THRESHOLD_HATED = -50  # Below this, neutrals attack
REP_THRESHOLD_FRIENDLY = 50 # Above this, discounts/perks

# Kill Consequences (Reputation Change)
REP_KILL_PENALTY_SAME_FACTION = -25 # Killing a friendly if you are friendly
REP_KILL_REWARD_HOSTILE = 5         # Killing a hostile
