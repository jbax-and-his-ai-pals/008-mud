# engine/world/encounters.py
"""Encounter zones: somewhere that walking is dangerous.

A zone is content (`data/encounters/*.json`, each file an object of zones keyed by id):

    "plain_near": {
        "region": "overworld",
        "rooms": ["plain_a", "plain_b"],              # optional: only these rooms; absent: every room of the region
        "monsters": ["slime", {"npc": "drakee", "weight": 3}],   # NPC template ids, each with an optional weight (default 1)
        "chance": 0.2,                                 # the chance, on arriving in one of its rooms, that something finds the player
        "count": [1, 2],                               # optional: how many (a number, or [least, most]; default 1)
        "cooldown": 20,                                # optional: seconds after one before another may (default 0)
        "message": "{name} appears!",                  # optional: said when it does; {name} is what came
        "when": {"not": {"kind": "flag", "flag": "won"}},   # optional: a condition the player must meet for the zone to be live
        "note": "for the author"
    }

When a player arrives in a room a zone covers (by walking, or by being taken there), it is not a safe place and no hostile is
already there, the zone rolls. What comes is an ordinary creature of the named template, placed in the room, hostile and
aggressive; it is not one of the room's own and does not come back after it dies, and it is gone if the player leaves the room
without it (it was only passing). A player under a `repel` status (an `apply_effect` whose `tags` include `repel`: a spell,
a consumable) is not found by creatures whose attack is below their own defence.
"""

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from engine.utils.logger import Logger

ENCOUNTERS_DIRECTORY = "encounters"
ENCOUNTER_KEYS = ("region", "rooms", "monsters", "chance", "count", "cooldown", "message", "when", "note")
REPEL_TAG = "repel"
INSTANCE_MARK = "encounter"          # NPC property: this creature came from a zone
DEFAULT_MESSAGE = "{name} appears!"


def monster_entries(definition: Dict[str, Any]) -> List[Tuple[str, float]]:
    """(template id, weight) for each monster a zone names."""
    out: List[Tuple[str, float]] = []
    for entry in definition.get("monsters") or []:
        if isinstance(entry, str):
            out.append((entry, 1.0))
        elif isinstance(entry, dict) and isinstance(entry.get("npc"), str):
            weight = entry.get("weight", 1)
            out.append((entry["npc"], float(weight) if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight > 0 else 1.0))
    return out


def count_range(definition: Dict[str, Any]) -> Tuple[int, int]:
    raw = definition.get("count", 1)
    if isinstance(raw, (list, tuple)) and len(raw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in raw):
        return max(1, int(raw[0])), max(1, int(raw[1]))
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(1, raw), max(1, raw)
    return 1, 1


class EncounterZones:
    def __init__(self, world: Any):
        self.world = world
        self.zones: Dict[str, Dict[str, Any]] = {}
        self._rng = random.Random()
        self._last_roll: Dict[str, float] = {}     # player id -> when a zone last found them
        self._sequence = 0

    # -- loading ---------------------------------------------------------------
    def add(self, zone_id: str, definition: Dict[str, Any]) -> None:
        self.zones[str(zone_id)] = definition

    def load(self, content_root: Optional[str]) -> int:
        self.zones = {}
        if not content_root:
            return 0
        directory = os.path.join(str(content_root), ENCOUNTERS_DIRECTORY)
        if not os.path.isdir(directory):
            return 0
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError) as error:
                Logger.warning("Encounters", "Could not read %s: %s" % (name, error))
                continue
            if not isinstance(payload, dict):
                Logger.warning("Encounters", "%s must be an object of zones" % name)
                continue
            for zone_id, definition in payload.items():
                if not str(zone_id).startswith("_") and isinstance(definition, dict):
                    self.add(zone_id, definition)
        return len(self.zones)

    # -- the zone a room is in -----------------------------------------------------
    def zones_for(self, region_id: str, room_id: str) -> List[str]:
        found = []
        for zone_id, definition in self.zones.items():
            if definition.get("region") != region_id:
                continue
            rooms = definition.get("rooms")
            if isinstance(rooms, list) and rooms and room_id not in rooms:
                continue
            found.append(zone_id)
        return found

    # -- on arriving -------------------------------------------------------------
    def leave(self, region_id: Optional[str], room_id: Optional[str]) -> None:
        """What came out of a zone and was not dealt with is gone when the player has moved on."""
        if not region_id or not room_id:
            return
        for npc in list(self.world.npcs.values()):
            props = getattr(npc, "properties", None) or {}
            if props.get(INSTANCE_MARK) and npc.is_alive and (npc.current_region_id, npc.current_room_id) == (region_id, room_id):
                if not self._anyone_here(region_id, room_id):
                    self.world.remove_npcs(npc.obj_id)

    def _anyone_here(self, region_id: str, room_id: str) -> bool:
        return any(getattr(p, "is_alive", False) and (p.current_region_id, p.current_room_id) == (region_id, room_id)
                   for p in self.world.players.values())

    def roll(self, player: Any, region_id: str, room_id: str) -> str:
        """Maybe something finds `player`, who has just arrived: the line they read, or ""."""
        zone_ids = self.zones_for(region_id, room_id)
        if not zone_ids or not getattr(player, "is_alive", False):
            return ""
        if self.world.is_location_safe(region_id, room_id):
            return ""
        from engine.world import factions

        if factions.hostiles_in(self.world, region_id, room_id):
            return ""
        now = float(self.world.clock.now())
        from engine import conditions

        for zone_id in zone_ids:
            definition = self.zones[zone_id]
            if definition.get("when") and not conditions.evaluate(definition["when"], player).satisfied:
                continue
            cooldown = definition.get("cooldown", 0)
            last = self._last_roll.get(getattr(player, "obj_id", ""))
            if isinstance(cooldown, (int, float)) and cooldown > 0 and last is not None and now - last < cooldown:
                continue
            chance = definition.get("chance", 0)
            if not isinstance(chance, (int, float)) or isinstance(chance, bool) or self._rng.random() >= chance:
                continue
            line = self._spawn(player, zone_id, definition, region_id, room_id)
            if line:
                self._last_roll[getattr(player, "obj_id", "")] = now
                return line
        return ""

    def force(self, player: Any, zone_id: str) -> str:
        """Call something out of a zone now (a tune that draws a creature): chance, cooldown and the zone's `when` do not apply.
        The line the player reads, or "" when the zone does not exist or nothing could come."""
        definition = self.zones.get(zone_id)
        if definition is None or not getattr(player, "is_alive", False):
            return ""
        return self._spawn(player, zone_id, definition, player.current_region_id, player.current_room_id)

    def _candidates(self, player: Any, definition: Dict[str, Any]) -> List[Tuple[str, float]]:
        entries = monster_entries(definition)
        entries = [(npc_id, weight) for npc_id, weight in entries if npc_id in self.world.npc_templates]
        if not player.has_effect_tag(REPEL_TAG):
            return entries
        defence = float(player.get_defense())
        # Under a repel, what could not hurt them keeps away: its attack is below what they stand in.
        return [(npc_id, weight) for npc_id, weight in entries
                if float((self.world.npc_templates.get(npc_id) or {}).get("attack_power", 0) or 0) >= defence]

    def _spawn(self, player: Any, zone_id: str, definition: Dict[str, Any], region_id: str, room_id: str) -> str:
        candidates = self._candidates(player, definition)
        if not candidates:
            return ""
        low, high = count_range(definition)
        how_many = self._rng.randint(low, high)
        names: List[str] = []
        for _ in range(how_many):
            template_id = self._rng.choices([c[0] for c in candidates], weights=[c[1] for c in candidates], k=1)[0]
            self._sequence += 1
            npc, status = self.world.spawn_npc(template_id, region_id, room_id, "%s_enc_%d" % (template_id, self._sequence))
            if npc is None or status != "spawned":
                continue
            npc.properties[INSTANCE_MARK] = zone_id
            npc.properties["respawn_cooldown"] = -1      # it was passing through: it does not come back
            npc.properties["wander_chance"] = 0
            npc.properties["move_cooldown"] = 9999
            npc.faction = "hostile"
            npc.behavior_type = "aggressive"
            names.append(npc.name)
        if not names:
            return ""
        template = definition.get("message") if isinstance(definition.get("message"), str) and definition["message"].strip() else DEFAULT_MESSAGE
        shown = names[0] if len(set(names)) == 1 and len(names) == 1 else ", ".join(names)
        try:
            return template.format(name=shown)
        except (KeyError, IndexError, ValueError):
            return DEFAULT_MESSAGE.format(name=shown)
