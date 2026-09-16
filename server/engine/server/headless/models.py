# engine/server/headless/models.py
"""Plain data carried across HeadlessServer and its headless/* mixins.

Split out from headless_server.py so mixin files that construct a Session
or Party at runtime (not just as a type hint) can import it directly
without a circular import back through headless_server.py itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Session:
    session_id: str
    player_id: str
    capabilities: List[str] = field(default_factory=list)
    entitlements: List[str] = field(default_factory=list)
    connected: bool = False
    disconnected_at: float | None = None
    # "player" or "test". Controls whether debug/GM tooling is reachable and
    # (later) whether engine internals are shown. See docs/design/WORLD_DESIGN.md §2.
    presentation_mode: str = "test"


@dataclass
class Party:
    party_id: str
    leader_player_id: str
    member_player_ids: List[str] = field(default_factory=list)
