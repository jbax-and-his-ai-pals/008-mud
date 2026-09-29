# engine/world/triggers.py
"""Something happens when the player walks into a room.

A trigger is `{on, when, once, effects}`, kept in `data/triggers/*.json` (each file an
object of triggers keyed by id) and running the same effect vocabulary a conversation
does (`engine/dialogue/effects.py`). It is not gated on any capability: a set with no
quests can still have a door that seals behind you.

    "boss_door": {
        "on":      {"event": "on_enter", "region": "mossroot", "room": "boss_hall"},
        "when":    {"kind": "has_item", "item_id": "item_key_mossroot"},   # optional
        "once":    "player",                                               # or "world", or false
        "effects": {"seal_exit": {"region": "mossroot", "room": "boss_hall", "direction": "east"},
                    "message": "The door grinds shut behind you."}
    }

`World._arrive` fires it after the player's location is set and *before* the room is
described, so an exit it reveals is in the room text. The text it produces is appended
to what the player reads on arrival.

`once` is `player` (the default; a flag on the player, `_trigger.<id>`, which saves with
the character), `world` (a latch in `world.world_state["triggers"]`, which the world
snapshot keeps) or `false` (every time). The latch is set *before* the effects run, so an
effect that arrives somewhere cannot fire the same trigger again.

Two limits keep a badly written set from hanging the server: triggers that fire from
inside triggers stop at `MAX_DEPTH`, and `World.teleport_player` caps chained arrivals.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from engine.dialogue.effects import apply_effects
from engine.utils.logger import Logger

TRIGGERS_DIRECTORY = "triggers"

# The events a trigger can be `on`. `on_enter` needs a region and a room.
TRIGGER_EVENTS = ("on_enter",)
# What a trigger may carry, and what `once` may be (`False` is "every time").
TRIGGER_KEYS = ("on", "when", "once", "effects", "note")
ONCE_MODES = ("player", "world")
DEFAULT_ONCE = "player"

MAX_DEPTH = 3
PLAYER_LATCH_PREFIX = "_trigger."


class TriggerRunner:
    def __init__(self, world):
        self.world = world
        self.triggers: Dict[str, Dict[str, Any]] = {}
        self._depth = 0

    # -- loading ---------------------------------------------------------------
    def add(self, trigger_id: str, definition: Dict[str, Any]) -> None:
        self.triggers[str(trigger_id)] = definition

    def load(self, content_root: Optional[str]) -> int:
        """Read `data/triggers/*.json`. A malformed file or trigger is reported and skipped;
        content validation refuses it before the game runs, so this is the safety net."""
        self.triggers = {}
        if not content_root:
            return 0
        directory = os.path.join(str(content_root), TRIGGERS_DIRECTORY)
        if not os.path.isdir(directory):
            return 0
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError) as error:
                Logger.warning("Triggers", "Could not read %s: %s" % (name, error))
                continue
            if not isinstance(payload, dict):
                Logger.warning("Triggers", "%s must be an object of triggers" % name)
                continue
            for trigger_id, definition in payload.items():
                if str(trigger_id).startswith("_") or not isinstance(definition, dict):
                    continue
                if trigger_id in self.triggers:
                    Logger.warning("Triggers", "trigger '%s' is defined twice; the first wins" % trigger_id)
                    continue
                self.add(trigger_id, definition)
        return len(self.triggers)

    # -- firing ----------------------------------------------------------------
    def fire_on_enter(self, player, region_id: str, room_id: str) -> List[str]:
        """Run every `on_enter` trigger for this room; the lines the player reads."""
        lines: List[str] = []
        if player is None or self._depth >= MAX_DEPTH:
            return lines
        for trigger_id, definition in self.triggers.items():
            on = definition.get("on")
            if not isinstance(on, dict) or on.get("event") != "on_enter":
                continue
            if (on.get("region"), on.get("room")) != (region_id, room_id):
                continue
            lines.extend(self._run(trigger_id, definition, player))
        return lines

    def _run(self, trigger_id: str, definition: Dict[str, Any], player) -> List[str]:
        once = definition.get("once", DEFAULT_ONCE)
        if once is not False and self._latched(trigger_id, once, player):
            return []
        condition = definition.get("when")
        if condition:
            from engine import conditions

            if not conditions.evaluate(condition, player).satisfied:
                return []
        if once is not False:
            self._latch(trigger_id, once, player)
        self._depth += 1
        try:
            report = apply_effects(definition.get("effects"), {"player": player, "world": self.world})
        except Exception as error:  # noqa: BLE001 - content must not stop a player arriving
            Logger.warning("Triggers", "trigger '%s' raised: %s" % (trigger_id, error))
            return []
        finally:
            self._depth -= 1
        for failure in report.failed:
            Logger.warning("Triggers", "trigger '%s': %s" % (trigger_id, failure))
        message = report.message()
        return [message] if message else []

    # -- latches ---------------------------------------------------------------
    def _latched(self, trigger_id: str, once: Any, player) -> bool:
        if once == "world":
            return bool((getattr(self.world, "world_state", {}).get("triggers") or {}).get(trigger_id))
        return bool((getattr(player, "flags", None) or {}).get(PLAYER_LATCH_PREFIX + trigger_id))

    def _latch(self, trigger_id: str, once: Any, player) -> None:
        if once == "world":
            self.world.world_state.setdefault("triggers", {})[trigger_id] = True
            return
        if not isinstance(getattr(player, "flags", None), dict):
            player.flags = {}
        player.flags[PLAYER_LATCH_PREFIX + trigger_id] = True
