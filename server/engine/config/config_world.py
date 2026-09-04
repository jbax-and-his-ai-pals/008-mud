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
FACTION_RELATIONSHIP_MATRIX = {
    "player": {
        "player": 100, "player_minion": 100, "friendly": 100,
        "neutral": 0, "hostile": -100
    },
    "player_minion": {
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
    }
}

# --- Reputation Thresholds ---
REP_THRESHOLD_HATED = -50  # Below this, neutrals attack
REP_THRESHOLD_FRIENDLY = 50 # Above this, discounts/perks

# Kill Consequences (Reputation Change)
REP_KILL_PENALTY_SAME_FACTION = -25 # Killing a friendly if you are friendly
REP_KILL_REWARD_HOSTILE = 5         # Killing a hostile
