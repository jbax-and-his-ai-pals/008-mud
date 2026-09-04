# engine/world/spawner.py
"""
Handles the logic for dynamically spawning monsters in the game world.
Optimized to only process the active region.
"""
import random
from typing import TYPE_CHECKING

from engine.config import (SPAWN_CHANCE_PER_TICK, SPAWN_DEBUG,
                         SPAWN_INTERVAL_SECONDS, SPAWN_MAX_MONSTERS_PER_REGION_CAP,
                         SPAWN_MIN_MONSTERS_PER_REGION, SPAWN_ROOMS_PER_MONSTER)
from engine.npcs.npc_factory import NPCFactory
from engine.utils.utils import weighted_choice
from engine.world.region import Region

if TYPE_CHECKING:
    from engine.world.world import World


class Spawner:
    def __init__(self, world: 'World'):
        self.world = world
        self.last_spawn_time = 0

    def update(self, current_time: float):
        """Main update tick for the spawner."""
        if current_time - self.last_spawn_time < SPAWN_INTERVAL_SECONDS:
            return
        self.last_spawn_time = current_time

        if random.random() > SPAWN_CHANCE_PER_TICK:
            return

        # Spawn around active players rather than a singleton cursor.
        # This keeps multiplayer sessions from starving other regions while
        # still limiting work to regions with active participants.
        active_region_ids = {
            player.current_region_id
            for player in self.world.players.values()
            if getattr(player, "current_region_id", None)
        }
        if not active_region_ids:
            fallback_player = self.world.resolve_reference_player()
            if fallback_player and fallback_player.current_region_id:
                active_region_ids.add(fallback_player.current_region_id)

        for region_id in active_region_ids:
            current_region = self.world.get_region(region_id)
            if current_region:
                self._spawn_monsters_in_region(current_region)

    def _count_monsters_in_region(self, region_id: str) -> int:
        """Counts active hostile monsters currently in a region."""
        return sum(1 for npc in self.world.npcs.values() if
                   npc and npc.current_region_id == region_id and
                   npc.faction == "hostile" and npc.is_alive)

    def _spawn_monsters_in_region(self, region: Region):
        """Attempts to spawn a monster in a suitable room within a given region."""
        if self.world.is_location_safe(region.obj_id) or not region.spawner_config:
            return

        num_rooms = len(region.rooms)
        if num_rooms <= 0: return

        # Determine the dynamic monster limit for this region
        ratio = SPAWN_ROOMS_PER_MONSTER
        min_limit = SPAWN_MIN_MONSTERS_PER_REGION
        max_cap = SPAWN_MAX_MONSTERS_PER_REGION_CAP
        calculated_limit = max(1, num_rooms // max(1, ratio))
        dynamic_max_for_region = max(min_limit, min(calculated_limit, max_cap))

        current_monster_count = self._count_monsters_in_region(region.obj_id)
        if current_monster_count >= dynamic_max_for_region:
            return

        # Find a suitable room to spawn in (not an active player's room, not a no-spawn zone)
        suitable_rooms = []
        blocked_locations = {
            (getattr(player, "current_region_id", None), getattr(player, "current_room_id", None))
            for player in self.world.players.values()
            if getattr(player, "current_region_id", None) and getattr(player, "current_room_id", None)
        }
        if not blocked_locations:
            fallback_player = self.world.resolve_reference_player()
            if fallback_player and fallback_player.current_region_id and fallback_player.current_room_id:
                blocked_locations.add((fallback_player.current_region_id, fallback_player.current_room_id))
        for room_id, room in region.rooms.items():
            if not room: continue
            if room.get_property('no_monster_spawn', False): continue
            
            room_name_lower = room.name.lower()
            room_id_lower = room_id.lower()
            no_spawn_keywords = self.world.ruleset_section("spawning").get("no_spawn_keywords", [])
            if any(str(keyword).lower() in room_id_lower or str(keyword).lower() in room_name_lower for keyword in no_spawn_keywords): continue
            
            # Don't spawn into any active player's current room
            if (region.obj_id, room_id) in blocked_locations: continue
            suitable_rooms.append(room_id)

        if not suitable_rooms: return
        room_id_to_spawn = random.choice(suitable_rooms)

        # Choose a monster from the region's weighted list
        region_monster_weights = region.spawner_config.get("monster_types", {})
        if not region_monster_weights: return
        monster_template_id = weighted_choice(region_monster_weights)
        if not monster_template_id or monster_template_id not in self.world.npc_templates: return

        level_range = region.spawner_config.get("level_range", [1, 1])
        level = random.randint(level_range[0], level_range[1])
        
        overrides = {
            "level": level,
            "current_region_id": region.obj_id,
            "current_room_id": room_id_to_spawn,
            "home_region_id": region.obj_id,
            "home_room_id": room_id_to_spawn
        }
        monster = NPCFactory.create_npc_from_template(monster_template_id, self.world, **overrides)

        if monster:
            self.world.add_npc(monster)
            if SPAWN_DEBUG and self.world.game:
                 self.world.game.renderer.add_message(f"[SpawnerDebug] Spawned {monster.name} in {region.obj_id}:{room_id_to_spawn}")
