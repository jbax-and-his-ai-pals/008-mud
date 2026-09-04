# engine/world/respawn_manager.py
"""
Manages the respawning of NPCs after they have been defeated.
"""
import time
from typing import TYPE_CHECKING, List, Dict, Any

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, NAMED_NPC_RESPAWN_COOLDOWN
from engine.npcs.npc import NPC
from engine.npcs.npc_factory import NPCFactory

if TYPE_CHECKING:
    from engine.world.world import World

class RespawnManager:
    def __init__(self, world: 'World'):
        self.world = world
        self.respawn_queue: List[Dict[str, Any]] = []

    def add_to_queue(self, npc: NPC):
        """Adds data for a defeated NPC to the respawn queue."""
        respawn_data = {
            "template_id": npc.template_id,
            "instance_id": npc.obj_id,
            "name": npc.name,
            "home_region_id": npc.home_region_id,
            "home_room_id": npc.home_room_id,
            "respawn_time": time.time() + NAMED_NPC_RESPAWN_COOLDOWN
        }
        self.respawn_queue.append(respawn_data)

    def update(self, current_time: float) -> List[str]:
        """Checks the respawn queue and recreates NPCs whose timers have expired."""
        messages = []
        remaining_in_queue = []
        respawned_this_tick = False

        for data in self.respawn_queue:
            if current_time >= data["respawn_time"]:
                overrides = {
                    "current_region_id": data["home_region_id"],
                    "current_room_id": data["home_room_id"]
                }
                new_npc = NPCFactory.create_npc_from_template(
                    data["template_id"], self.world, data["instance_id"], **overrides
                )
                if new_npc:
                    self.world.add_npc(new_npc)
                    respawned_this_tick = True
                    # Notify all players currently in that room
                    for p in self.world.players.values():
                        if p.current_room_id == data["home_room_id"] and p.current_region_id == data["home_region_id"]:
                            messages.append(f"{FORMAT_HIGHLIGHT}{new_npc.name} has returned.{FORMAT_RESET}")
                            break  # one message per respawn event
            else:
                remaining_in_queue.append(data)
        
        if respawned_this_tick:
            self.respawn_queue = remaining_in_queue

        return messages