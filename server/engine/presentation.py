"""Presentation mode: what the engine shows a player versus a tester.

The engine has two audiences and used to show them the same text. A tester needs
precise state -- charges remaining, days until a node recovers, why a task is
unavailable, exact effect durations. A player should see the world: content that
simply is not offered yet, a patch that has been picked clean, a recipe they
have not learned how to make.

Resolution order is **session -> world -> default**:

  1. The `session_id` in the command context, if the world's server can resolve
     it. This is the live game path.
  2. The world's `server` attribute, if a session associated with the player is
     in player mode.
  3. `DEFAULT_MODE`, which is `"test"`.

`"test"` as the fallback is deliberate. Anything that cannot be identified as a
player session -- a unit-test world with no server attached, an operator script,
the journey lab -- keeps today's exact output. That is the safety rail that lets
this change land without rewriting the existing suite, and it is why the mode is
resolved rather than assumed.

The mirror of that decision lives at the server entry points, which *do* default
to `player` (`JsonLineMudServer`, `JsonWebSocketMudServer`,
`launch_content_set.py`). Together: real players get player mode, and everything
else keeps working.

Content can author both voices too. Where a system has a `text` block, a
`player`/`test` sub-key overrides the flat string for that mode -- see
`variant()`.

This module lives at `engine/presentation.py` rather than under
`engine/server/` deliberately: `engine/server/__init__.py` imports the whole
headless runtime, so anything under that package drags the server into modules
like `engine/items/resource_node.py` and creates an import cycle. It has no
engine imports of its own and is therefore safe to import from anywhere.
"""

from __future__ import annotations

from typing import Any, Optional

MODE_PLAYER = "player"
MODE_TEST = "test"
VALID_MODES = (MODE_PLAYER, MODE_TEST)

# What an unresolvable mode falls back to. See the module docstring.
DEFAULT_MODE = MODE_TEST


def _coerce(mode: Any) -> Optional[str]:
    """Return a valid mode, or None when the value is not usable."""
    if not isinstance(mode, str):
        return None
    normalized = mode.strip().lower()
    return normalized if normalized in VALID_MODES else None


def session_mode(session: Any) -> Optional[str]:
    return _coerce(getattr(session, "presentation_mode", None))


def resolve_mode(context: Optional[dict] = None) -> str:
    """Resolve the presentation mode for a command or display context."""
    if not isinstance(context, dict):
        return DEFAULT_MODE

    world = context.get("world")
    server = getattr(world, "server", None) if world is not None else None

    # 1. The session that issued this command.
    session_id = context.get("session_id")
    if server is not None and session_id:
        sessions = getattr(server, "sessions", None)
        if isinstance(sessions, dict):
            mode = session_mode(sessions.get(session_id))
            if mode:
                return mode

    # 2. A session associated with the acting player.
    if server is not None:
        player = context.get("player")
        player_id = getattr(player, "obj_id", None)
        sessions = getattr(server, "sessions", None)
        if player_id and isinstance(sessions, dict):
            for session in sessions.values():
                if getattr(session, "player_id", None) != player_id:
                    continue
                mode = session_mode(session)
                if mode:
                    return mode

    # 3. The world's own default (set by the server that created it).
    server_default = _coerce(getattr(server, "default_presentation_mode", None))
    if server_default:
        return server_default

    return DEFAULT_MODE


def is_player_mode(context: Optional[dict] = None) -> bool:
    return resolve_mode(context) == MODE_PLAYER


def show_internals(context: Optional[dict] = None) -> bool:
    """Whether engine internals (counts, timers, lock reasons) may be shown.

    True in test mode, False for players.
    """
    return not is_player_mode(context)


def resolve_mode_for_player(world: Any, player: Any) -> str:
    """Resolve the mode for display code that only has a world and a player.

    Used by shared formatters (`format_name_for_display`) that are called from
    both the text client and the pygame renderer and therefore have no command
    context.

    When several sessions are attached to the same player -- possible in a
    shared world, and in tests -- player mode wins. Being shown too little is a
    cosmetic problem; leaking engine internals to a player is the thing this
    module exists to prevent.
    """
    if world is None:
        return DEFAULT_MODE
    server = getattr(world, "server", None)
    if server is None:
        return DEFAULT_MODE
    sessions = getattr(server, "sessions", None)
    player_id = getattr(player, "obj_id", None)
    if player_id and isinstance(sessions, dict):
        modes = {
            mode
            for session in sessions.values()
            if getattr(session, "player_id", None) == player_id
            for mode in (session_mode(session),)
            if mode
        }
        if MODE_PLAYER in modes:
            return MODE_PLAYER
        if modes:
            return next(iter(modes))
    return _coerce(getattr(server, "default_presentation_mode", None)) or DEFAULT_MODE


def is_player_mode_for_player(world: Any, player: Any) -> bool:
    return resolve_mode_for_player(world, player) == MODE_PLAYER


def variant(value: Any, context: Optional[dict] = None) -> Any:
    """Pick a mode-specific variant from content-authored text.

    A content author writes::

        "text": {
            "test": "The herb bed has been depleted. (2 days remaining)",
            "player": "You've picked this patch clean."
        }

    A plain string is returned unchanged, and a dict without a variant for the
    active mode falls back to `default`, then to the first string found.
    """
    if not isinstance(value, dict):
        return value
    mode = resolve_mode(context)
    for key in (mode, "default"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate
    for candidate in value.values():
        if isinstance(candidate, str):
            return candidate
    return value
