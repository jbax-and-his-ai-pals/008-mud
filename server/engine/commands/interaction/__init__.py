# engine/commands/interaction/__init__.py
"""
Interaction commands package.
Exports handlers to be discovered by the command system.
"""
from .observation import look_handler, examine_handler, read_handler
from .pickup_drop import get_handler, drop_handler
from .containers import open_handler, close_handler, put_handler
from .use_give import use_handler, give_handler
from .npcs import (
    talk_handler, ask_handler, follow_handler, guide_handler, turnin_handler
)
from .info import collection_status_handler
from .environment import interact_handler, pick_handler
