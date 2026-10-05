# engine/world/vehicles.py
"""Vehicles: something a player boards to go where they cannot go on foot, and leaves parked where they set it down.

A vehicle is content (`data/vehicles/*.json`, each file an object of vehicles keyed by id):

    "skimmer": {
        "name": "the skimmer",
        "description": "A flat-bottomed craft that rides the sand as a boat rides the sea.",
        "start": {"region": "ashmere", "room": "boathouse"},     # where it waits at the start (optional)
        "board_text": "You climb aboard.",                         # optional
        "disembark_text": "You climb down.",                       # optional
        "lands_in_biomes": ["desert"],                             # where it may be set down (absent: anywhere)
        "note": "for the author"
    }

A way that needs one is an exit requirement `{"type": "vehicle", "vehicle": "skimmer"}` (an id or a list of
them). A room may name vehicles it can always be set down in, whatever its region's biome, with
`properties.docks: ["skimmer"]`. `embark` and `disembark` are the player's commands; the `place_vehicle`,
`board_vehicle` and `disembark_vehicle` effects and the `aboard` condition are the story's.

Where each vehicle is lives in `world.world_state["vehicles"]` (which the world snapshot keeps): `{region, room,
aboard}` where `aboard` is the id of the player who is riding it, or None when it is parked. What a player rides
is `player.flags["_vehicle"]`, saved with the character. A vehicle goes where its rider goes; a rider who dies
leaves it parked where it was and walks away from the wreck at respawn.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from engine.utils.logger import Logger

VEHICLES_DIRECTORY = "vehicles"
VEHICLE_KEYS = ("name", "description", "start", "board_text", "disembark_text", "lands_in_biomes", "note")
STATE_KEY = "vehicles"
FLAG = "_vehicle"
DEFAULT_BOARD_TEXT = "You climb aboard %s."
DEFAULT_DISEMBARK_TEXT = "You climb down from %s."


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


class VehicleRegistry:
    def __init__(self, world: Any):
        self.world = world
        self.vehicles: Dict[str, Dict[str, Any]] = {}

    # -- loading ---------------------------------------------------------------
    def add(self, vehicle_id: str, definition: Dict[str, Any]) -> None:
        self.vehicles[str(vehicle_id)] = definition

    def load(self, content_root: Optional[str]) -> int:
        """Read `data/vehicles/*.json`. A malformed file is reported and skipped; content validation refuses it first."""
        self.vehicles = {}
        if not content_root:
            return 0
        directory = os.path.join(str(content_root), VEHICLES_DIRECTORY)
        if not os.path.isdir(directory):
            return 0
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError) as error:
                Logger.warning("Vehicles", "Could not read %s: %s" % (name, error))
                continue
            if not isinstance(payload, dict):
                Logger.warning("Vehicles", "%s must be an object of vehicles" % name)
                continue
            for vehicle_id, definition in payload.items():
                if not str(vehicle_id).startswith("_") and isinstance(definition, dict):
                    self.add(vehicle_id, definition)
        return len(self.vehicles)

    # -- state -----------------------------------------------------------------
    def _all(self) -> Dict[str, Any]:
        state = self.world.world_state.get(STATE_KEY)
        if not isinstance(state, dict):
            state = self.world.world_state[STATE_KEY] = {}
        return state

    def _state(self, vehicle_id: str) -> Optional[Dict[str, Any]]:
        """The vehicle's record, made from its `start` the first time anything asks."""
        state = self._all()
        if vehicle_id not in state:
            start = (self.vehicles.get(vehicle_id) or {}).get("start")
            if not isinstance(start, dict):
                return None
            state[vehicle_id] = {"region": start.get("region"), "room": start.get("room"), "aboard": None}
        return state[vehicle_id]

    def name_of(self, vehicle_id: str) -> str:
        return str((self.vehicles.get(vehicle_id) or {}).get("name") or vehicle_id)

    def parked_in(self, region_id: str, room_id: str) -> List[str]:
        found = []
        for vehicle_id in sorted(self.vehicles):
            record = self._state(vehicle_id)
            if record and record.get("aboard") is None and (record.get("region"), record.get("room")) == (region_id, room_id):
                found.append(vehicle_id)
        return found

    def aboard(self, player: Any) -> Optional[str]:
        flags = getattr(player, "flags", None)
        value = flags.get(FLAG) if isinstance(flags, dict) else None
        return value if value in self.vehicles else None

    def place(self, vehicle_id: str, region_id: str, room_id: str) -> bool:
        """Set a vehicle down somewhere (a story moving it). Whoever was riding it is put ashore, so it is not in two places."""
        if vehicle_id not in self.vehicles:
            return False
        record = self._all().get(vehicle_id)
        if record and record.get("aboard"):
            rider = self.world.get_player_by_id(record["aboard"])
            if rider is not None and isinstance(getattr(rider, "flags", None), dict):
                rider.flags.pop(FLAG, None)
        self._all()[vehicle_id] = {"region": region_id, "room": room_id, "aboard": None}
        return True

    # -- the rider -------------------------------------------------------------
    def board(self, player: Any, vehicle_id: str) -> str:
        record = self._state(vehicle_id)
        flags = player.flags if isinstance(getattr(player, "flags", None), dict) else None
        if vehicle_id not in self.vehicles or flags is None:
            return "There is nothing like that to board."
        if self.aboard(player):
            return "You are already aboard %s." % self.name_of(self.aboard(player))
        if not record or record.get("aboard") is not None or (record.get("region"), record.get("room")) != (player.current_region_id, player.current_room_id):
            return "%s is not here." % _capital(self.name_of(vehicle_id))
        record["aboard"] = player.obj_id
        flags[FLAG] = vehicle_id
        text = (self.vehicles[vehicle_id].get("board_text") or DEFAULT_BOARD_TEXT % self.name_of(vehicle_id))
        return str(text)

    def can_land(self, vehicle_id: str, region_id: str, room_id: str) -> bool:
        definition = self.vehicles.get(vehicle_id) or {}
        allowed = definition.get("lands_in_biomes")
        if not isinstance(allowed, list) or not allowed:
            return True
        region = self.world.get_region(region_id)
        room = region.get_room(room_id) if region else None
        docks = room.properties.get("docks") if room is not None and isinstance(room.properties, dict) else None
        if isinstance(docks, list) and vehicle_id in docks:
            return True
        return getattr(region, "biome", None) in allowed

    def disembark(self, player: Any) -> str:
        vehicle_id = self.aboard(player)
        if vehicle_id is None:
            return "You are not aboard anything."
        if not self.can_land(vehicle_id, player.current_region_id, player.current_room_id):
            return "You cannot set %s down here." % self.name_of(vehicle_id)
        self._all()[vehicle_id] = {"region": player.current_region_id, "room": player.current_room_id, "aboard": None}
        player.flags.pop(FLAG, None)
        text = self.vehicles[vehicle_id].get("disembark_text") or DEFAULT_DISEMBARK_TEXT % self.name_of(vehicle_id)
        return str(text)

    def follow(self, player: Any) -> None:
        """The vehicle goes where its rider goes (called on every arrival)."""
        vehicle_id = self.aboard(player)
        record = self._all().get(vehicle_id) if vehicle_id else None
        if record is not None:
            record["region"], record["room"] = player.current_region_id, player.current_room_id

    def abandon(self, player: Any) -> None:
        """A rider who dies leaves the vehicle where it was parked, or where they fell."""
        vehicle_id = self.aboard(player)
        if vehicle_id is None:
            return
        record = self._all().get(vehicle_id)
        if record is not None:
            record["aboard"] = None
        player.flags.pop(FLAG, None)

    def requirement_met(self, player: Any, requirement: Dict[str, Any]) -> bool:
        wanted = requirement.get("vehicle")
        wanted = [wanted] if isinstance(wanted, str) else (wanted if isinstance(wanted, list) else [])
        return self.aboard(player) in wanted

    def parked_line(self, region_id: str, room_id: str) -> str:
        names = [self.name_of(vehicle_id) for vehicle_id in self.parked_in(region_id, room_id)]
        if not names:
            return ""
        return " ".join("%s waits here." % _capital(name) for name in names)

