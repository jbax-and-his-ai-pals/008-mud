"""Where a server keeps what it has to remember across a restart.

The same root `World` uses for save files (`MUD_STATE_DIR` first, then the user's
local application data, then `~/.local/share`), so one variable moves everything a
game keeps and a test can point it at a scratch directory.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_root() -> Path:
    configured = os.environ.get("MUD_STATE_DIR", "").strip()
    if configured and configured.lower() not in {"none", "null"}:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    return Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"


def default_database_path(content_set_id: str) -> str:
    """`<state root>/single_player_mud/state/<content set>.sqlite3`: one game, one file."""
    safe = "".join(c for c in str(content_set_id) if c.isalnum() or c in ("_", "-", ".")) or "game"
    return str((state_root() / "single_player_mud" / "state" / ("%s.sqlite3" % safe)).resolve())
