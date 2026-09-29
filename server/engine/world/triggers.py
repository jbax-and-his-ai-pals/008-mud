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

Three events fire a trigger:

    on_enter      the player walks into `region`/`room`. `World._arrive` fires it after the
                  location is set and *before* the room is described, so an exit it
                  reveals is in the room text.
    npc_killed    a creature dies: `npc` is a template id or a placed id, optionally
                  narrowed to the `region`/`room` it died in.
    room_cleared  the last living hostile in `region`/`room` is gone.

The kill events are raised by `World.dispatch_event("npc_killed", ...)`, from the player's
blows, a spell, a minion, and the world tick's reaper (a creature that died of something
that never called `die()`). The text a trigger produces is appended to what the player
reads at that moment.

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

# The events a trigger can be `on`, the fields each event's `on` may carry, and the ones it
# needs. `region` and `room` always come as a pair. `TriggerSchema.gd` is the editor's copy.
TRIGGER_EVENTS = ("on_enter", "npc_killed", "room_cleared")
EVENT_FIELDS = {
    "on_enter": ("region", "room"),
    "npc_killed": ("npc", "region", "room"),
    "room_cleared": ("region", "room"),
}
EVENT_REQUIRED = {
    "on_enter": ("region", "room"),
    "npc_killed": ("npc",),
    "room_cleared": ("region", "room"),
}
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

    def fire_npc_killed(self, player, npc) -> List[str]:
        """The lines for a creature's death: `npc_killed` triggers, then `room_cleared` if it
        was the last hostile standing. `player` is who to run the effects for (the killer,
        else someone in the room, else the primary player); with nobody, nothing fires."""
        if npc is None or self._depth >= MAX_DEPTH:
            return []
        region_id, room_id = getattr(npc, "current_region_id", None), getattr(npc, "current_room_id", None)
        player = player or self._player_for(region_id, room_id)
        if player is None:
            return []
        lines: List[str] = []
        for trigger_id, definition in self.triggers.items():
            on = definition.get("on")
            if not isinstance(on, dict) or on.get("event") != "npc_killed":
                continue
            if on.get("npc") not in (getattr(npc, "template_id", None), getattr(npc, "obj_id", None)):
                continue
            if "region" in on and (on.get("region"), on.get("room")) != (region_id, room_id):
                continue
            lines.extend(self._run(trigger_id, definition, player))
        from engine.world import factions

        if region_id and room_id and factions.is_hostile(npc, self.world) \
                and not factions.hostiles_in(self.world, region_id, room_id):
            for trigger_id, definition in self.triggers.items():
                on = definition.get("on")
                if isinstance(on, dict) and on.get("event") == "room_cleared" \
                        and (on.get("region"), on.get("room")) == (region_id, room_id):
                    lines.extend(self._run(trigger_id, definition, player))
        return lines

    def _player_for(self, region_id: str, room_id: str):
        for candidate in getattr(self.world, "players", {}).values():
            if (candidate.current_region_id, candidate.current_room_id) == (region_id, room_id):
                return candidate
        return self.world.resolve_reference_player(None)

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
