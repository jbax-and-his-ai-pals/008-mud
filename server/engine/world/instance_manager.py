# engine/world/instance_manager.py
import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room

if TYPE_CHECKING:
    from engine.world.world import World

class InstanceManager:
    def __init__(self, world: 'World'):
        self.world = world

    def _resolve_reference_player(self, requesting_player=None):
        if not self.world:
            return None
        return self.world.resolve_reference_player(requesting_player)

    def _find_player_with_completed_quest(self, quest_id: str):
        for player in getattr(self.world, "players", {}).values():
            if player.runtime_state.quests is None:
                continue
            if quest_id in player.runtime_state.quests.completed:
                return player
        reference_player = self.world.resolve_reference_player()
        if reference_player is not None and reference_player.runtime_state.quests is not None:
            if quest_id in reference_player.runtime_state.quests.completed:
                return reference_player
        return None

    def build_region(
        self, unique_region_id: str, region_name: str, region_description: str,
        rooms_data: Dict[str, Any], entry_point: Dict[str, Any],
        region_properties: Optional[Dict[str, Any]] = None,
        exit_requirements: Optional[Dict[str, Any]] = None,
    ) -> Tuple['Region', str]:
        """Builds a Region from a {room_id: {name, description, exits}} dict
        (the shape both quest instances and houses use, including the
        'dynamic_exit' sentinel for a room that should lead back to the
        permanent entry room), registers it on the world, and records
        entry_point metadata on the region so apply_entry_exit can wire (or
        re-wire, e.g. after a save/load) its door onto a real, permanent
        room. Does NOT wire the door itself -- callers that need other setup
        first (e.g. spawning NPCs into the new region) should call
        apply_entry_exit once everything else has succeeded, matching the
        order quest instantiation already relied on.
        """
        new_region = Region(obj_id=unique_region_id, name=region_name, description=region_description)
        new_region.properties = region_properties if region_properties is not None else {}

        entry_room_id = ""
        for room_id, room_data in rooms_data.items():
            if not entry_room_id: entry_room_id = room_id
            for direction, exit_dest in list(room_data.get('exits', {}).items()):
                if exit_dest == "dynamic_exit":
                    room_data['exits'][direction] = f"{entry_point['region_id']}:{entry_point['room_id']}"
                elif ":" not in exit_dest:
                    room_data['exits'][direction] = f"{unique_region_id}:{exit_dest}"

            new_room = Room.from_dict(room_data)
            new_region.add_room(room_id, new_room)

        self.world.regions[unique_region_id] = new_region
        new_region.properties["entry_point"] = {
            "region_id": entry_point['region_id'],
            "room_id": entry_point['room_id'],
            "exit_command": entry_point['exit_command'],
            "destination": f"{unique_region_id}:{entry_room_id}",
            "exit_requirements": exit_requirements,
        }
        return new_region, entry_room_id

    def apply_entry_exit(self, region: 'Region') -> bool:
        """Wires (or re-wires) a region's entry_point metadata onto its
        permanent room's exits. Safe to call repeatedly, including after a
        save/load restores the region -- the permanent room's own region is
        rebuilt fresh from static content on every load, which silently
        drops any exit wired onto it at runtime unless this is replayed.
        Returns True if wiring was applied, False if the metadata or the
        target room couldn't be resolved (mirrors the historical silent-skip
        behavior of quest-instance creation).
        """
        meta = region.properties.get("entry_point")
        if not meta:
            return False
        perm_region = self.world.get_region(meta.get("region_id"))
        if not perm_region:
            return False
        perm_room = perm_region.get_room(meta.get("room_id"))
        if not perm_room:
            return False
        perm_room.exits[meta["exit_command"]] = meta["destination"]
        exit_reqs = meta.get("exit_requirements")
        if exit_reqs:
            reqs = perm_room.properties.get("exit_requirements", {})
            reqs[meta["exit_command"]] = exit_reqs
            perm_room.update_property("exit_requirements", reqs)
        return True

    def remove_entry_exit(self, region: 'Region') -> None:
        """Removes a region's wired exit from its permanent room, if present."""
        meta = region.properties.get("entry_point")
        if not meta:
            return
        perm_region = self.world.get_region(meta.get("region_id"))
        perm_room = perm_region.get_room(meta.get("room_id")) if perm_region else None
        if perm_room and meta.get("exit_command") in perm_room.exits:
            del perm_room.exits[meta["exit_command"]]

    def instantiate_quest_region(self, quest_data: Dict[str, Any], requesting_player=None) -> Tuple[bool, str, Optional[str]]:
        # Use explicitly provided player or fall back to a loaded reference player.
        active_player = self._resolve_reference_player(requesting_player)
        if not active_player:
            return False, "Cannot instantiate region without a player.", None

        try:
            entry_point = quest_data['entry_point']
            instance_region = quest_data['instance_region']
            quest_instance_id = quest_data['instance_id']
            quest_manager = getattr(self.world, "quest_manager", None)
            objective = (quest_manager.get_active_objective(quest_data) if quest_manager else None) \
                or quest_data.get("objective", {})
            layout_config = quest_data.get("layout_generation_config", {})

            unique_region_id = f"instance_{quest_instance_id}"
            quest_data['instance_region_id'] = unique_region_id

            new_region, entry_room_id = self.build_region(
                unique_region_id=unique_region_id,
                region_name=instance_region['region_name'],
                region_description=instance_region['region_description'],
                rooms_data=instance_region['rooms'],
                entry_point=entry_point,
                region_properties=instance_region.get("properties", {}),
            )

            target_template_id = objective.get("target_template_id")
            target_count_range = layout_config.get("target_count", [2, 4])
            num_to_spawn = random.randint(target_count_range[0], target_count_range[1])
            spawnable_room_ids = [rid for rid in new_region.rooms.keys() if rid != entry_room_id]
            
            if not target_template_id: return False, f"Quest '{quest_instance_id}' has no target creature.", None
            
            for _ in range(num_to_spawn):
                if not spawnable_room_ids: break 
                chosen_room_id = random.choice(spawnable_room_ids)
                npc = NPCFactory.create_npc_from_template(
                    target_template_id, self.world,
                    current_region_id=unique_region_id, current_room_id=chosen_room_id
                )
                if not npc:
                    # The quest hasn't been marked completed yet, so
                    # cleanup_quest_region() would find nothing to clean up
                    # here -- remove the just-created region directly instead.
                    self._remove_region_and_npcs(unique_region_id)
                    return False, f"Could not spawn required creature '{target_template_id}'.", None
                self.world.add_npc(npc)

            permanent_entry_region = self.world.get_region(entry_point['region_id'])
            if not permanent_entry_region: return False, "Could not get permanent entry region.", None
            self.apply_entry_exit(new_region)

            giver_npc_id = None
            spawn_message = "You decide to take on the task."
            giver_tid = quest_data.get("giver_npc_template_id")
            if giver_tid:
                giver_instance_id = f"giver_{quest_instance_id}"
                giver_npc = NPCFactory.create_npc_from_template(
                    giver_tid, self.world, giver_instance_id,
                    current_region_id=active_player.current_region_id,
                    current_room_id=active_player.current_room_id
                )
                if giver_npc:
                    self.world.add_npc(giver_npc)
                    giver_npc_id = giver_npc.obj_id
                    spawn_message = (f"{giver_npc.name} notices you taking their notice from the board and approaches you.\n"
                                     f"\"{giver_npc.dialog.get('greeting', 'Please help me!')}\"")
                else:
                    # Same as above: the quest was never marked completed,
                    # so cleanup_quest_region() is a no-op here. Remove the
                    # region/NPCs directly, plus the permanent exit link
                    # already written above if it was set.
                    self.remove_entry_exit(new_region)
                    self._remove_region_and_npcs(unique_region_id)
                    return False, f"Could not spawn giver NPC '{giver_tid}'.", None

            return True, spawn_message, giver_npc_id

        except KeyError as e: return False, f"Quest template is missing a required key: {e}", None
        except Exception as e:
            import traceback; traceback.print_exc()
            return False, f"An unexpected error occurred: {e}", None

    def cleanup_quest_region(self, quest_id: str, requesting_player=None):
        active_player = self._resolve_reference_player(requesting_player)
        if not active_player or active_player.runtime_state.quests is None or quest_id not in active_player.runtime_state.quests.completed:
            active_player = self._find_player_with_completed_quest(quest_id)
        if not active_player or active_player.runtime_state.quests is None or quest_id not in active_player.runtime_state.quests.completed:
            return
        quest_data = active_player.runtime_state.quests.completed[quest_id]
        
        # 1. Cleanup Standard Instances
        instance_region_id = quest_data.get("instance_region_id")
        entry_point = quest_data.get("entry_point")

        if instance_region_id and entry_point:
            perm_region = self.world.get_region(entry_point['region_id'])
            if perm_region:
                perm_room = perm_region.get_room(entry_point['room_id'])
                if perm_room and entry_point['exit_command'] in perm_room.exits:
                    del perm_room.exits[entry_point['exit_command']]

            self._remove_region_and_npcs(instance_region_id)
            
        # 2. Cleanup Procedurally Generated Saga Regions
        if "generated_region_ids" in quest_data:
            for region_id in quest_data["generated_region_ids"]:
                # Also need to find and remove the entrance link in the parent region
                # Since we don't store the exact link pos easily, we scan exits or rely on it being okay (dangling exits are bad though).
                # Actually, QuestGenerator linked them.
                # To clean up properly, we should ideally search for exits pointing TO this region.
                self._remove_links_to_region(region_id)
                self._remove_region_and_npcs(region_id)

        # Move to archive
        del active_player.runtime_state.quests.completed[quest_id]
        active_player.runtime_state.quests.archived[quest_id] = quest_data

    def _remove_region_and_npcs(self, region_id: str):
        npcs_to_remove = [npc.obj_id for npc in self.world.npcs.values() if npc.current_region_id == region_id]
        for npc_id in npcs_to_remove: del self.world.npcs[npc_id]
        if region_id in self.world.regions: del self.world.regions[region_id]
        
    def _remove_links_to_region(self, target_region_id: str):
        """Scans all regions to remove exits pointing to the target region."""
        for region in self.world.regions.values():
            if region.obj_id == target_region_id: continue
            for room in region.rooms.values():
                exits_to_remove = []
                for dir, dest in room.exits.items():
                    if dest.startswith(f"{target_region_id}:"):
                        exits_to_remove.append(dir)
                for dir in exits_to_remove:
                    del room.exits[dir]

    def check_and_cleanup_completed_instances(self):
        all_players = list(self.world.players.values())
        if not all_players:
            fallback_player = self.world.resolve_reference_player()
            if fallback_player is not None:
                all_players = [fallback_player]
        for player in all_players:
            if not player or player.runtime_state.quests is None:
                continue
            self._cleanup_for_player(player)

    def _cleanup_for_player(self, player):
        for quest_id in list(player.runtime_state.quests.completed.keys()):
            quest_data = player.runtime_state.quests.completed[quest_id]
            
            # Logic: Only clean up if player is NOT in any of the regions associated with the quest
            regions_to_check = []
            if quest_data.get("instance_region_id"):
                regions_to_check.append(quest_data.get("instance_region_id"))
            if quest_data.get("generated_region_ids"):
                regions_to_check.extend(quest_data.get("generated_region_ids"))
            
            if not regions_to_check: continue # Nothing to clean
            
            if player.current_region_id not in regions_to_check:
                self.cleanup_quest_region(quest_id, requesting_player=player)
