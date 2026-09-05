# engine/world/world.py
import heapq
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING

from engine.campaign.campaign_manager import CampaignManager
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, DEFAULT_SAVE_FILE, WORLD_UPDATE_INTERVAL,
    REP_KILL_PENALTY_SAME_FACTION, REP_KILL_REWARD_HOSTILE, FORMAT_SUCCESS, DEFAULT_CURRENCY_NAME
)
# UPDATED IMPORT
from engine.core.quests import QuestManager

from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.player import Player
from engine.player.aspects import PlayerGameAspects
from engine.world.region import Region
from engine.world.room import Room
from engine.items.item import Item
from engine.items.lockpick import Lockpick
from engine.npcs.npc import NPC
from engine.world.spawner import Spawner
from engine.world.save_manager import SaveManager
from engine.world.definition_loader import load_all_definitions, initialize_new_world
from engine.world.respawn_manager import RespawnManager
from engine.world.instance_manager import InstanceManager
from engine.utils.pathfinding import find_path
from engine.core.skill_system import SkillSystem
from engine.config.config_combat import configure_combat_elements
from engine.items.affix_data import configure_item_affixes

from engine.world.description_generator import generate_room_description

if TYPE_CHECKING:
    from engine.core.game_manager import GameManager

class World:
    def __init__(self, content_set: Any = None, save_directory: Optional[str] = None):
        if content_set is None:
            raise ValueError("World requires a validated content set.")
        package_root = os.path.abspath(str(content_set.content_root))
        self.content_root = package_root
        configure_combat_elements(self.content_root)
        configure_item_affixes(self.content_root)
        self.content_set = content_set
        self.save_directory = self._resolve_save_directory(save_directory)
        self.enabled_capabilities = frozenset(content_set.capabilities)
        self.player_aspects = PlayerGameAspects.from_world(self)
        self.regions: Dict[str, Region] = {}
        self.item_templates: Dict[str, Dict[str, Any]] = {}
        self.npc_templates: Dict[str, Dict[str, Any]] = {}
        self.players: Dict[str, 'Player'] = {}
        self._primary_player_id: Optional[str] = None
        self.npcs: Dict[str, NPC] = {}
        self.quest_board: List[Dict[str, Any]] = []
        
        self.quest_manager = (
            QuestManager(self)
            if self.has_capability("quests")
            else None
        )
        self.campaign_manager = (
            CampaignManager(self)
            if self.has_capability("quests")
            else None
        )
        self.spawner = Spawner(self)
        self.save_manager = SaveManager(self)
        self.respawn_manager = RespawnManager(self)
        self.instance_manager = InstanceManager(self)

        self.last_update_time = 0.0
        self.game: Optional['GameManager'] = None

        load_all_definitions(self)

    def _resolve_save_directory(self, configured_directory: Optional[str]) -> str:
        """Return the writable, content-set-scoped location for save files."""
        if configured_directory:
            return str(Path(configured_directory).expanduser().resolve())
        configured_root = os.environ.get("MUD_STATE_DIR", "").strip()
        if configured_root and configured_root.lower() not in {"none", "null"}:
            state_root = Path(configured_root).expanduser()
        else:
            local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
            state_root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
        return str((state_root / "single_player_mud" / "saves" / self.content_set.content_set_id).resolve())
    def has_capability(self, capability: str) -> bool:
        """Return whether this package has enabled an optional system."""
        return self.content_set.game_contract.system_enabled(capability, False)

    def ruleset_system_enabled(self, system: str, default: bool = True) -> bool:
        """Read an optional system toggle from the selected content ruleset.

        Capability selection answers whether the engine constructs a
        subsystem. Ruleset toggles answer how this package presents it.
        """
        return self.content_set.game_contract.system_enabled(system, default)

    def uses_progression(self) -> bool:
        """Whether the selected game presents level-based character growth."""
        return self.ruleset_system_enabled("progression")

    def apply_content_player_defaults(self, player: Any) -> None:
        """Normalize a player to the selected game's enabled aspects."""
        self.player_aspects.normalize(player)

    def _player_defaults(self) -> dict[str, Any]:
        raw = self.content_set.ruleset.get("player_defaults", {})
        return raw if isinstance(raw, dict) else {}

    def initial_magic_spells(self) -> tuple[str, ...]:
        magic = self._player_defaults().get("magic", {})
        raw_spells = magic.get("known_spells", []) if isinstance(magic, dict) else []
        if not isinstance(raw_spells, list):
            return ()
        return tuple(str(spell_id).strip() for spell_id in raw_spells if str(spell_id).strip())

    def initial_inventory(self) -> list[dict[str, Any] | str]:
        raw_items = self._player_defaults().get("starting_inventory", [])
        return list(raw_items) if isinstance(raw_items, list) else []

    def ruleset_section(self, name: str) -> dict[str, Any]:
        raw = self.content_set.ruleset.get(name, {})
        return raw if isinstance(raw, dict) else {}

    def currency_name(self) -> str:
        """Display name for this content set's currency (e.g. "gold", "credits")."""
        raw = self.ruleset_section("economy").get("currency_name")
        name = raw.strip() if isinstance(raw, str) else ""
        return name or DEFAULT_CURRENCY_NAME

    def initialize_content_player(self, player: Any) -> None:
        """Apply authored starting state to a newly created player only."""
        self.apply_content_player_defaults(player)
        if player.runtime_state.magic is not None:
            player.runtime_state.magic.known_spells = set(self.initial_magic_spells())



    @property
    def player(self) -> Optional['Player']:
        return self.players.get(self._primary_player_id) if self._primary_player_id else None

    @player.setter
    def player(self, p: Optional['Player']):
        if p:
            self.players[p.obj_id] = p
            self._primary_player_id = p.obj_id
        else:
            if self._primary_player_id in self.players:
                del self.players[self._primary_player_id]
            self._primary_player_id = None

    @property
    def current_region_id(self) -> Optional[str]:
        return self.player.current_region_id if self.player else None

    @current_region_id.setter
    def current_region_id(self, val: str):
        pass

    @property
    def current_room_id(self) -> Optional[str]:
        return self.player.current_room_id if self.player else None

    @current_room_id.setter
    def current_room_id(self, val: str):
        pass

    def initialize_new_world(self, start_region: str | None = None, start_room: str | None = None):
        initialize_new_world(
            self,
            start_region or self.content_set.start_region_id,
            start_room or self.content_set.start_room_id,
        )

    def load_save_game(self, filename: str = DEFAULT_SAVE_FILE) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        return self.save_manager.load(filename)

    def save_game(self, filename: str = DEFAULT_SAVE_FILE, player: Optional['Player'] = None) -> bool:
        return self.save_manager.save(filename, player=player)

    def resolve_reference_player(
        self,
        player: Optional['Player'] = None,
        player_id: Optional[str] = None,
    ) -> Optional['Player']:
        if player is not None:
            return player
        if player_id:
            candidate = self.players.get(player_id)
            if candidate is not None:
                return candidate
        if self.player is not None:
            return self.player
        if self.players:
            return next(iter(self.players.values()), None)
        return None

    def update(self) -> List[Tuple[Optional[Tuple[str, str]], str]]:
        """Advances world state by one tick.

        Each returned message is paired with the (region_id, room_id) it
        occurred in (or None for messages with no single location), so the
        server can deliver it only to sessions actually watching that room
        instead of whichever session's poll happened to trigger this tick.
        """
        current_time_abs = time.time()
        messages: List[Tuple[Optional[Tuple[str, str]], str]] = []

        dt = current_time_abs - self.last_update_time

        if dt < WORLD_UPDATE_INTERVAL:
             return messages
        self.last_update_time = current_time_abs

        active_regions_rooms = set()
        for p in self.players.values():
            if p.current_region_id and p.current_room_id:
                active_regions_rooms.add((p.current_region_id, p.current_room_id))

        for reg_id, room_id in active_regions_rooms:
            region = self.get_region(reg_id)
            if region:
                room = region.get_room(room_id)
                if room:
                    room_msgs = room.update(dt)
                    messages.extend(((reg_id, room_id), msg) for msg in room_msgs)

        messages.extend(self.respawn_manager.update(current_time_abs))
        self.spawner.update(current_time_abs)

        npcs_to_update = [npc for npc in self.npcs.values() if npc.is_alive]
        for npc in npcs_to_update:
            npc_message = npc.update(self, current_time_abs)
            if npc_message:
                messages.append(((npc.current_region_id, npc.current_room_id), npc_message))

        if self.quest_manager:
            for player in list(self.players.values()):
                self.quest_manager.check_quest_completion(player)

        npcs_to_remove = [npc_id for npc_id, npc in self.npcs.items() if not npc.is_alive]
        for npc_id in npcs_to_remove: self.npcs.pop(npc_id, None)

        self.instance_manager.check_and_cleanup_completed_instances()
        
        return messages

    def find_path(self, source_region_id: str, source_room_id: str, target_region_id: str, target_room_id: str) -> Optional[List[str]]:
        return find_path(self, source_region_id, source_room_id, target_region_id, target_room_id)

    def add_to_respawn_queue(self, npc: NPC):
        self.respawn_manager.add_to_queue(npc)

    def look(self, minimal: bool = False, player: Optional['Player'] = None) -> str:
        return generate_room_description(self, minimal, player=player)

    def change_room(self, direction: str, player: Optional['Player'] = None) -> str:
        active_player = self.resolve_reference_player(player)
        if not active_player or not active_player.is_alive:
             return f"{FORMAT_ERROR}You cannot move while dead.{FORMAT_RESET}"
        
        old_region_id = active_player.current_region_id
        old_room_id = active_player.current_room_id
        current_room = self.get_current_room(active_player)
        
        if not old_region_id or not old_room_id or not current_room:
            return f"{FORMAT_ERROR}You are lost in an unknown place and cannot move.{FORMAT_RESET}"
        
        reqs = current_room.properties.get("exit_requirements", {})
        dir_req = reqs.get(direction)
        
        if dir_req:
            req_type = dir_req.get("type")
            if req_type == "skill":
                skill = dir_req.get("skill_name")
                difficulty = dir_req.get("difficulty", 10)
                fail_msg = dir_req.get("failure_message", "You fail to traverse the path.")
                
                success, roll_msg = SkillSystem.attempt_check(active_player, skill, difficulty)
                if not success:
                    return f"{FORMAT_ERROR}{fail_msg}{FORMAT_RESET} (Requires {skill} {difficulty}+)"
            
            elif req_type == "locked":
                key_id = dir_req.get("key_id")
                has_key = any(slot.item and slot.item.obj_id == key_id for slot in active_player.inventory.slots)
                if not has_key:
                    return f"{FORMAT_ERROR}The way {direction} is locked.{FORMAT_RESET}"

        destination_id = current_room.get_exit(direction)
        if not destination_id: return f"{FORMAT_ERROR}You cannot go {direction}.{FORMAT_RESET}"
        
        new_region_id, new_room_id = (destination_id.split(":") if ":" in destination_id else (old_region_id, destination_id))
        
        if not new_region_id:
            return f"{FORMAT_ERROR}You are lost and cannot determine your region.{FORMAT_RESET}"
        
        target_region = self.get_region(new_region_id)
        if not target_region:
             return f"{FORMAT_ERROR}That path leads to an unknown region.{FORMAT_RESET}"
             
        target_room = target_region.get_room(new_room_id)
        if not target_room:
            return f"{FORMAT_ERROR}That path leads to an unknown place.{FORMAT_RESET}"

        target_lock_key = target_room.get_property("locked_by")
        if target_lock_key:
             has_key = any(slot.item and slot.item.obj_id == target_lock_key for slot in active_player.inventory.slots)
             if not has_key:
                  return f"{FORMAT_ERROR}The door to {target_room.name} is locked.{FORMAT_RESET}"

        target_room.visited = True
        active_player.current_region_id = new_region_id
        active_player.current_room_id = new_room_id

        # NEW: Get quest updates (returns list of strings instead of printing)
        quest_updates = []
        if self.quest_manager:
            quest_updates = self.quest_manager.handle_room_entry(active_player)

        if new_region_id.startswith("instance_"):
            for quest in active_player.runtime_state.quests.active.values():
                if quest.get("instance_region_id") == new_region_id:
                    quest["completion_check_enabled"] = True
                    break

        region_change_msg = f"{FORMAT_HIGHLIGHT}You have entered {target_region.name}.{FORMAT_RESET}\n\n" if new_region_id != old_region_id else ""
        
        # Assemble Final Output
        output = region_change_msg + self.look(minimal=True, player=active_player)
        
        # Append quest updates at the bottom so they are seen last
        if quest_updates:
            output += "\n\n" + "\n\n".join(quest_updates)

        return output

    def dispatch_event(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        if event_type == "npc_killed":
            quest_msg = self.quest_manager.handle_npc_killed(event_type, data) if self.quest_manager else None
            rep_msg = self._handle_reputation_on_kill(data)
            
            if quest_msg and rep_msg: return f"{quest_msg}\n{rep_msg}"
            return quest_msg or rep_msg
        return None

    def _handle_reputation_on_kill(self, data: Dict[str, Any]) -> Optional[str]:
        player = data.get("player")
        npc = data.get("npc")
        if not player or not npc: return None
        
        faction = npc.faction
        if faction == "hostile":
            player.adjust_reputation("friendly", REP_KILL_REWARD_HOSTILE)
            return None 
        elif faction == "friendly" or faction == "neutral":
            player.adjust_reputation("friendly", REP_KILL_PENALTY_SAME_FACTION)
            player.adjust_reputation("neutral", REP_KILL_PENALTY_SAME_FACTION)
            return f"{FORMAT_ERROR}Your reputation plummets! You are now looked upon with suspicion.{FORMAT_RESET}"
        return None

    def attempt_pick_lock_direction(self, direction: str, player: Optional['Player'] = None) -> str:
        active_player = self.resolve_reference_player(player)
        current_room = self.get_current_room(active_player)
        if not current_room: return "You are nowhere."
        
        reqs = current_room.properties.get("exit_requirements", {})
        dir_req = reqs.get(direction)
        
        if dir_req and dir_req.get("type") == "locked":
            difficulty = dir_req.get("pick_difficulty", 999)
            if difficulty > 100: return "This lock cannot be picked."
            
            has_lockpick = False
            if not active_player: return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
            for slot in active_player.inventory.slots:
                if isinstance(slot.item, Lockpick):
                    has_lockpick = True
                    break
            
            if not has_lockpick:
                return "You need a lockpick."
                
            success, msg = SkillSystem.attempt_check(active_player, "lockpicking", difficulty)
            if success:
                del reqs[direction]
                current_room.update_property("exit_requirements", reqs)
                SkillSystem.grant_xp(active_player, "lockpicking", difficulty)
                return f"{FORMAT_SUCCESS}Click! You unlock the way {direction}.{FORMAT_RESET}"
            else:
                return f"{FORMAT_ERROR}You fail to pick the lock.{FORMAT_RESET}"

        dest_id = current_room.get_exit(direction)
        if dest_id:
            rid = getattr(active_player, "current_region_id", None)
            if ":" in dest_id: rid, dest_id = dest_id.split(":")

            reg = self.get_region(rid) if rid else None
            if reg:
                room = reg.get_room(dest_id)
                if room and room.get_property("locked_by"):
                    difficulty = 20 
                    
                    has_lockpick = False
                    if not active_player: return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
                    for slot in active_player.inventory.slots:
                        if isinstance(slot.item, Lockpick):
                            has_lockpick = True
                            break

                    if not has_lockpick: return "You need a lockpick."
                    success, msg = SkillSystem.attempt_check(active_player, "lockpicking", difficulty)
                    if success:
                        room.properties["locked_by"] = None 
                        SkillSystem.grant_xp(active_player, "lockpicking", 10)
                        return f"{FORMAT_SUCCESS}Click! You unlock the door to {room.name}.{FORMAT_RESET}"
                    else:
                        return f"{FORMAT_ERROR}You fail to pick the lock.{FORMAT_RESET}"

        return "There is nothing locked in that direction."

    def _load_room_items_from_save(self, room_items_data: Dict[str, Any]):
        for location_key, item_refs in room_items_data.items():
            try:
                region_id, room_id = location_key.split(":")
                region = self.get_region(region_id)
                room = region.get_room(room_id) if region else None
                if room:
                    for item_ref in item_refs:
                        if item_ref and "item_id" in item_ref:
                            item = ItemFactory.create_item_from_template(item_ref["item_id"], self, **item_ref.get("properties_override", {}))
                            if item: room.add_item(item)
            except ValueError:
                print(f"Warning: Could not parse room location key '{location_key}' from save file.")

    def get_region(self, region_id: str) -> Optional[Region]: return self.regions.get(region_id)
    
    def get_current_region(self, player: Optional['Player'] = None) -> Optional[Region]: 
        active_player = self.resolve_reference_player(player)
        region_id = getattr(active_player, "current_region_id", None)
        return self.regions.get(region_id) if region_id else None
    
    def get_current_room(self, player: Optional['Player'] = None) -> Optional[Room]:
        active_player = self.resolve_reference_player(player)
        region = self.get_current_region(active_player)
        room_id = getattr(active_player, "current_room_id", None)
        if region and room_id:
            return region.get_room(room_id)
        return None

    def get_room_for_player(self, player: Optional['Player']) -> Optional[Room]:
        if not player:
            return None
        region_id = getattr(player, "current_region_id", None)
        room_id = getattr(player, "current_room_id", None)
        if not region_id or not room_id:
            return None
        region = self.get_region(region_id)
        if not region:
            return None
        return region.get_room(room_id)

    def add_region(self, region_id: str, region: Region) -> None: self.regions[region_id] = region

    def get_player_by_id(self, player_id: Optional[str]) -> Optional['Player']:
        if not player_id:
            return None
        return self.players.get(str(player_id))

    def get_players_in_room(
        self,
        region_id: str,
        room_id: str,
        *,
        alive_only: bool = False,
    ) -> List['Player']:
        players = [
            player
            for player in self.players.values()
            if getattr(player, "current_region_id", None) == region_id
            and getattr(player, "current_room_id", None) == room_id
        ]
        if alive_only:
            players = [player for player in players if getattr(player, "is_alive", False)]
        return players

    def get_players_for_npc(self, npc: Optional[NPC], *, alive_only: bool = False) -> List['Player']:
        if not npc:
            return []
        region_id = getattr(npc, "current_region_id", None)
        room_id = getattr(npc, "current_room_id", None)
        if not region_id or not room_id:
            return []
        return self.get_players_in_room(region_id, room_id, alive_only=alive_only)

    def get_viewer_for_npc(self, npc: Optional[NPC], preferred_player: Optional['Player'] = None) -> Optional['Player']:
        if preferred_player is not None:
            players = self.get_players_for_npc(npc, alive_only=True)
            if preferred_player in players:
                return preferred_player
        players = self.get_players_for_npc(npc, alive_only=True)
        if players:
            return players[0]
        return None
    
    def add_npc(self, npc: NPC) -> None:
        npc.last_moved = time.time()
        npc.world = self
        self.npcs[npc.obj_id] = npc
    
    def get_npc(self, instance_id: str) -> Optional[NPC]: return self.npcs.get(instance_id)
    
    def get_npcs_in_room(self, region_id: str, room_id: str) -> List[NPC]:
        return [npc for npc in self.npcs.values() if npc.current_region_id == region_id and npc.current_room_id == room_id and npc.is_alive]

    def get_npcs_for_player(self, player: Optional['Player']) -> List[NPC]:
        if not player:
            return []
        region_id = getattr(player, "current_region_id", None)
        room_id = getattr(player, "current_room_id", None)
        if not region_id or not room_id:
            return []
        return self.get_npcs_in_room(region_id, room_id)
    
    def get_current_room_npcs(self, player: Optional['Player'] = None) -> List[NPC]:
        active_player = self.resolve_reference_player(player)
        rid = getattr(active_player, "current_region_id", None)
        rmid = getattr(active_player, "current_room_id", None)
        if not rid or not rmid: return []
        return self.get_npcs_in_room(rid, rmid)
    
    def get_items_in_room(self, region_id: str, room_id: str) -> List[Item]:
        region = self.get_region(region_id)
        if not region: return []
        room = region.get_room(room_id)
        return getattr(room, 'items', []) if room else []

    def get_items_for_player(self, player: Optional['Player']) -> List[Item]:
        if not player:
            return []
        region_id = getattr(player, "current_region_id", None)
        room_id = getattr(player, "current_room_id", None)
        if not region_id or not room_id:
            return []
        return self.get_items_in_room(region_id, room_id)
    
    def get_items_in_current_room(self, player: Optional['Player'] = None) -> List[Item]:
        active_player = self.resolve_reference_player(player)
        rid = getattr(active_player, "current_region_id", None)
        rmid = getattr(active_player, "current_room_id", None)
        if not rid or not rmid: return []
        return self.get_items_in_room(rid, rmid)
    
    def add_item_to_room(self, region_id: str, room_id: str, item: Item) -> bool:
        region = self.get_region(region_id)
        if not region: return False
        room = region.get_room(room_id)
        if room:
             room.add_item(item)
             return True
        return False
    
    def remove_item_from_room(self, region_id: str, room_id: str, obj_id: str) -> Optional[Item]:
         region = self.get_region(region_id)
         if not region: return None
         room = region.get_room(room_id)
         return room.remove_item(obj_id) if room else None
    
    def is_location_safe(self, region_id: str, room_id: Optional[str] = None) -> bool:
        region = self.get_region(region_id)
        if not region: return False
        return region.get_property("safe_zone", False)
    
    def is_location_outdoors(self, region_id: str, room_id: str) -> bool:
        region = self.get_region(region_id)
        if not region: return True
        room = region.get_room(room_id)
        if room:
            room_setting = room.get_property("outdoors")
            if room_setting is not None:
                return room_setting
        
        region_setting = region.get_property("outdoors")
        if region_setting is not None:
            return region_setting
        return True
    
    def find_item_in_room(self, name: str, player: Optional['Player'] = None) -> Optional[Item]:
         items = self.get_items_in_current_room(player)
         name_lower = name.lower()
         for item in items:
              if name_lower == item.name.lower() or name_lower == item.obj_id: return item
         for item in items:
              if name_lower in item.name.lower(): return item
         return None

    def find_item_in_room_for_player(self, name: str, player: Optional['Player']) -> Optional[Item]:
         items = self.get_items_for_player(player)
         name_lower = name.lower()
         for item in items:
              if name_lower == item.name.lower() or name_lower == item.obj_id: return item
         for item in items:
              if name_lower in item.name.lower(): return item
         return None

    def find_npc_in_room(self, name: str, player: Optional['Player'] = None) -> Optional[NPC]:
         npcs = self.get_current_room_npcs(player)
         name_lower = name.lower()
         for npc in npcs:
              if name_lower == npc.name.lower() or name_lower == npc.obj_id: return npc
         for npc in npcs:
              if name_lower in npc.name.lower(): return npc
         return None

    def find_npc_in_room_for_player(self, name: str, player: Optional['Player']) -> Optional[NPC]:
         npcs = self.get_npcs_for_player(player)
         name_lower = name.lower()
         for npc in npcs:
              if name_lower == npc.name.lower() or name_lower == npc.obj_id: return npc
         for npc in npcs:
              if name_lower in npc.name.lower(): return npc
         return None
    
    def get_player_status(self) -> str:
        if not self.player: return "Player not loaded."
        return self.player.get_status()
    
    def get_room_description_for_display(self, minimal: bool = False) -> str:
        return generate_room_description(self, minimal)
    
    def remove_item_instance_from_room(self, region_id: str, room_id: str, item_instance: Item) -> bool:
        region = self.get_region(region_id)
        if not region: return False
        room = region.get_room(room_id)
        if not room or not hasattr(room, 'items'): return False
        try:
            room.items.remove(item_instance)
            return True
        except ValueError:
            return False
    
    def find_nearest_safe_room(self, source_region_id: str, source_room_id: str) -> Optional[Tuple[str, str]]:
        if self.is_location_safe(source_region_id, source_room_id):
            return (source_region_id, source_room_id)
        candidate_paths = []
        for region_id, region in self.regions.items():
            if region.get_property("safe_zone", False):
                for room_id in region.rooms.keys():
                    path = self.find_path(source_region_id, source_room_id, region_id, room_id)
                    if path is not None:
                        heapq.heappush(candidate_paths, (len(path), (region_id, room_id)))
        if candidate_paths:
            return heapq.heappop(candidate_paths)[1]
        return None

    def instantiate_quest_region(self, quest_data: Dict[str, Any], requesting_player=None) -> Tuple[bool, str, Optional[str]]:
        return self.instance_manager.instantiate_quest_region(quest_data, requesting_player=requesting_player)

    def cleanup_quest_region(self, quest_id: str, requesting_player=None):
        self.instance_manager.cleanup_quest_region(quest_id, requesting_player=requesting_player)
