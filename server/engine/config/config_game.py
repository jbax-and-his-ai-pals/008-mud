# engine/config/config_game.py
"""
Configuration for core game systems, file paths, and debug settings.
"""
import os

# FIX: Import directly from the module to avoid circular dependency with engine.config
from engine.config.config_display import FORMAT_GRAY

# --- Directories and Files ---
# Calculate the Project Root based on the location of this config file
# config_game.py is in engine/config/, so we go up two levels to get to root.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAVE_GAME_DIR = os.path.join(DATA_DIR, "saves")
REGION_DIR = os.path.join(DATA_DIR, "regions")
ITEM_TEMPLATE_DIR = os.path.join(DATA_DIR, "items")
NPC_TEMPLATE_DIR = os.path.join(DATA_DIR, "npcs")
DEFAULT_SAVE_FILE = "default_save.json"
CAMPAIGN_DIR = os.path.join(DATA_DIR, "campaigns")

# --- System Settings ---
SCROLL_SPEED = 3
MAX_SCROLL_HISTORY = 1000
COMMAND_HISTORY_SIZE = 50
MAX_BUFFER_LINES = 50

# --- Debug Settings ---
DEBUG_IGNORE_PLAYER_COMBAT = False
DEBUG_SHOW_LEVEL = True

# --- Core Time System Settings ---
TIME_REAL_SECONDS_PER_GAME_DAY = 1200  # 20 minutes
TIME_DAYS_PER_WEEK = 7
TIME_DAYS_PER_MONTH = 30
TIME_MONTHS_PER_YEAR = 12
TIME_DAY_NAMES = [
    "Moonday", "Tideday", "Windday", "Thunderday",
    "Fireday", "Starday", "Sunday"
]
TIME_MONTH_NAMES = [
    "Deepwinter", "Icemelt", "Springbloom", "Rainshower",
    "Meadowgrow", "Highsun", "Fireheat", "Goldenfield",
    "Harvestide", "Leaffall", "Frostwind", "Darknight"
]

# --- REVISED TIME PERIOD THRESHOLDS ---
TIME_DAWN_HOUR = 5      # Dawn starts at 5:00
TIME_MORNING_HOUR = 8   # Morning starts at 8:00
TIME_AFTERNOON_HOUR = 12 # Afternoon starts at 12:00
TIME_DUSK_HOUR = 18     # Dusk starts at 18:00
TIME_NIGHT_HOUR = 21    # Night starts at 21:00
# Note: Anything before Dawn or after Night is considered "Night"

TIME_UPDATE_THRESHOLD = 0.001
TIME_MAX_CATCHUP_SECONDS = 5.0

# --- Weather System Settings ---
WEATHER_PERSISTENCE_CHANCE = 0.3
WEATHER_TRANSITION_CHANGE_CHANCE = 0.5
WEATHER_INTENSITY_WEIGHTS = [0.4, 0.3, 0.2, 0.1] # mild, moderate, strong, severe

# --- AI System Settings ---
AI_AMBIENT_ENABLED = True
AI_AMBIENT_INTERVAL_SECONDS = 5.0 # Time in seconds between ambient events
AI_AMBIENT_TEXT_COLOR = FORMAT_GRAY # The color for the ambient text