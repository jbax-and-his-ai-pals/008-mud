# engine/world/respawn_manager.py
"""
Manages the respawning of NPCs after they have been defeated.
"""
from typing import TYPE_CHECKING, List, Dict, Any, Tuple

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, NAMED_NPC_RESPAWN_COOLDOWN
from engine.npcs.npc import NPC
from engine.npcs.npc_factory import NPCFactory
from engine.world import placements

if TYPE_CHECKING:
    from engine.world.world import World

class RespawnManager:
    def __init__(self, world: 'World'):
        self.world = world
        self.respawn_queue: List[Dict[str, Any]] = []

    def add_to_queue(self, npc: NPC):
        """Adds data for a defeated NPC to the respawn queue."""
        placed_delay = npc.placed_respawn_seconds(self.world)
        respawn_data = {
            "template_id": npc.template_id,
            "instance_id": npc.obj_id,
            "name": npc.name,
            "home_region_id": npc.home_region_id,
            "home_room_id": npc.home_room_id,
            "respawn_time": self.world.clock.now() + (placed_delay if placed_delay is not None else NAMED_NPC_RESPAWN_COOLDOWN),
        }
        if placed_delay is not None:
            # A creature the room placed comes back as the room placed it, and not in front
            # of a player who is standing there: it waits until the room is empty.
            respawn_data["placed"] = True
        self.respawn_queue.append(respawn_data)

    def update(self, current_time: float) -> List[Tuple[Tuple[str, str], str]]:
        """Checks the respawn queue and recreates NPCs whose timers have expired.

        Each returned message is paired with the (region_id, room_id) it occurred
        in, so callers can deliver it only to sessions actually watching that room.
        """
        messages: List[Tuple[Tuple[str, str], str]] = []
        remaining_in_queue = []
        respawned_this_tick = False

        for data in self.respawn_queue:
            if current_time >= data["respawn_time"] and data.get("placed") and self._watched(data):
                remaining_in_queue.append(data)
                continue
            if current_time >= data["respawn_time"]:
                overrides = {
                    "current_region_id": data["home_region_id"],
                    "current_room_id": data["home_room_id"]
                }
                if data.get("placed"):
                    placement = placements.find_placement(
                        self.world, data["home_region_id"], data["home_room_id"], data["instance_id"])
                    if placement is not None:
                        overrides.update(placements.placement_overrides(placement))
                        overrides.update({"home_region_id": data["home_region_id"], "home_room_id": data["home_room_id"]})
                new_npc = NPCFactory.create_npc_from_template(
                    data["template_id"], self.world, data["instance_id"], **overrides
                )
                if new_npc:
                    self.world.add_npc(new_npc)
                    respawned_this_tick = True
                    # Notify all players currently in that room
                    for p in self.world.players.values():
                        if p.current_room_id == data["home_room_id"] and p.current_region_id == data["home_region_id"]:
                            location = (data["home_region_id"], data["home_room_id"])
                            messages.append((location, f"{FORMAT_HIGHLIGHT}{new_npc.name} has returned.{FORMAT_RESET}"))
                            break  # one message per respawn event
            else:
                remaining_in_queue.append(data)
        
        if respawned_this_tick:
            self.respawn_queue = remaining_in_queue

        return messages

    def _watched(self, data: Dict[str, Any]) -> bool:
        """A player is standing in the room the creature would come back in."""
        return any(
            p.current_room_id == data["home_room_id"] and p.current_region_id == data["home_region_id"]
            for p in self.world.players.values()
        )