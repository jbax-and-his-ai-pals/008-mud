# engine/config/__init__.py
"""
Initializes the config package, making all settings available for direct import.
This allows other modules to use `from engine.config import SETTING_NAME` without
knowing which specific file the setting is in.
"""

# Order matters for dependencies within config files
from .config_display import *
from .config_game import * 
from .config_combat import * 
from .config_commands import *
from .config_items import *
from .config_npc import *
from .config_player import *
from .config_quests import *
from .config_world import *