# engine/npcs/ai/__init__.py
"""
NPC Artificial Intelligence Package.
Handles decision making, movement, and specific behavior routines.
"""
from .dispatcher import handle_ai
from .schedules import initialize_npc_schedules
from .combat_logic import start_retreat, scan_for_targets