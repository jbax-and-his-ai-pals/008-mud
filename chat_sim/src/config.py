import os
import torch

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'characters.json')

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 620
FPS = 30

# Colors
COLOR_BG = (192, 192, 192)
COLOR_WINDOW = (255, 255, 255)
COLOR_TEXT = (0, 0, 0)
COLOR_SYSTEM = (100, 100, 100) # For "Bob has left the room"
COLOR_TITLE_BAR = (0, 0, 128)
COLOR_TITLE_TEXT = (255, 255, 255)
COLOR_BUTTON_LIGHT = (223, 223, 223)
COLOR_BUTTON_DARK = (128, 128, 128)

# Name Colors (AOL Style: distinctive, readable)
NAME_COLORS = [
    (0, 0, 255),      # Blue
    (255, 0, 0),      # Red
    (0, 128, 0),      # Green
    (128, 0, 128),    # Purple
    (255, 100, 0),    # Orange
    (0, 128, 128),    # Teal
    (165, 42, 42),    # Brown
    (255, 0, 255),    # Magenta
]

# LLM Settings
LLM_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
HISTORY_LIMIT = 5   
MAX_NEW_TOKENS = 60 

# Simulation Settings
NUM_STARTING_CHARS = 10       # Start with 3 people
ROSTER_CHECK_INTERVAL = 8000 # Check if someone should join/leave every 8 seconds
MIN_MSGS_BEFORE_LEAVE = 3    # Must chat 3 times before allowed to leave