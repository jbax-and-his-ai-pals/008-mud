# engine/world/world.py
import heapq
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING

from engine.campaign.campaign_manager import CampaignManager
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, DEFAULT_SAVE_FILE, WORLD_UPDATE_INTERVAL,
    REP_KILL_PENALTY_SAME_FACTION, REP_KILL_REWARD_HOSTILE, FORMAT_SUCCESS, DEFAULT_CURRENCY_NAME,
)
# UPDATED IMPORT
from engine.core import advancement
from engine.core.quests import QuestManager
from engine.core.clock import Clock, WallClock

from engine.items.item_factory import ItemFactory
from engine.naming import resolve_best
from engine.npcs.npc_factory import NPCFactory
from engine.player import Player
from engine.player.aspects import PlayerGameAspects
from engine.world.region import Region
from engine.world.room import Room
from engine.world import factions
from engine.items.item import Item
from engine.items.lockpick import Lockpick
from engine.npcs.npc import NPC
from engine.world.spawner import Spawner
from engine.world.save_manager import SaveManager
from engine.world.definition_loader import load_all_definitions, initialize_new_world
from engine.world.respawn_manager import RespawnManager
from engine.world.scenes import SceneRunner
from engine.world.triggers import TriggerRunner
from engine.world.instance_manager import InstanceManager
from engine.world.housing_manager import HousingManager, HOUSE_ENTRY_SENTINEL
from engine.core.crime_manager import CrimeManager
from engine.utils.pathfinding import find_path
from engine.utils.logger import Logger
from engine.core.skill_system import SkillSystem
from engine.config.config_combat import configure_combat_elements
from engine.items.affix_data import configure_item_affixes

from engine.world.description_generator import generate_room_description

if TYPE_CHECKING:
    from engine.core.game_manager import GameManager

class World:
    def __init__(self, content_set: Any = None, save_directory: Optional[str] = None, clock: Optional[Clock] = None):
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
        # Synthetic catch-all districts, built lazily per region when
        # `ruleset.world.regions.enforce_district_coverage` is on. See
        # `_hidden_district_for`.
        self._hidden_districts: Dict[str, Dict[str, Any]] = {}
        self.item_templates: Dict[str, Dict[str, Any]] = {}
        self.npc_templates: Dict[str, Dict[str, Any]] = {}
        self.players: Dict[str, 'Player'] = {}
        self._primary_player_id: Optional[str] = None
        self.npcs: Dict[str, NPC] = {}
        self.quest_board: List[Dict[str, Any]] = []
        # World-scoped flags content sets by triggers and effects (`once: world`).
        # It rides the world snapshot, so it survives a restart with the rest.
        self.world_state: Dict[str, Any] = {}
        # What content built, recorded once by `world_snapshot.record_baseline` so a
        # snapshot can carry only what changed since.
        self._content_baseline: Optional[Dict[str, Any]] = None

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
        # Not gated on a capability: a set with no quests can still have a door that
        # seals behind you. Loaded from `data/triggers/` once the definitions are.
        self.trigger_runner = TriggerRunner(self)
        # What the player watches (`data/scenes/`): beats told a moment apart, with things happening between them.
        self.scene_runner = SceneRunner(self)
        # Things to tell a particular player that are not the answer to their command (their share of a
        # kill someone else finished); the server delivers them to whichever session the player is on.
        self.pending_player_notices: List[Tuple[Any, str]] = []
        # Things to do a little later (the beats of a scene): (due time on the world clock, action).
        self.scheduled_actions: List[Tuple[float, Any, Optional[str]]] = []
        self.spawner = Spawner(self)
        self.save_manager = SaveManager(self)
        self.respawn_manager = RespawnManager(self)
        self.instance_manager = InstanceManager(self)
        self.housing_manager = HousingManager(self)
        self.crime_manager = CrimeManager(self)

        self.clock: Clock = clock or WallClock()
        self.last_update_time = 0.0
        self._simulation_has_started = False
        self.game: Optional['GameManager'] = None

        load_all_definitions(self)
        self.trigger_runner.load(self.content_root)
        self.scene_runner.load(self.content_root)

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

    def uses_abilities(self) -> bool:
        """Whether this package has abilities at all, and so an ability pool.

        `magic` is a content set saying its abilities are spells, which is a
        flavour rather than a mechanism; every set that declares it has
        abilities. The second check is the bridge for sets written before
        `abilities` existed as its own capability.
        """
        return self.has_capability("abilities") or self.has_capability("magic")

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

    def declared_status_stats(self) -> tuple[str, ...]:
        """Which stats this content set shows on a status line, if it says.

        Two places can say it, and both are content. `stats.order` in the
        contracts file is the general one -- the same section that says which
        stat fills which role, so a set that renames its stats renames them in
        one place. `ruleset.status.stats` is the older spelling and is still
        read, because a set written before the contract existed should not stop
        working.

        The status line itself reads the contract directly (see
        `engine/contracts/stats.py::display_stats`); this method is kept for
        callers that want just the list.
        """
        from engine.contracts import stats as stats_contract

        from_contract = tuple(stats_contract.declared_stat_order(self))
        if from_contract:
            return from_contract
        raw = self.ruleset_section("status").get("stats")
        if not isinstance(raw, list):
            return ()
        return tuple(str(stat).strip() for stat in raw if str(stat).strip())

    def quest_board_name(self) -> str:
        """Display name for this content set's quest board (e.g. "Job Board")."""
        raw = self.ruleset_section("quest_generation").get("board_display_name")
        name = raw.strip() if isinstance(raw, str) else ""
        return name or "Quest Board"

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
        current_time_abs = self.clock.now()
        messages: List[Tuple[Optional[Tuple[str, str]], str]] = []

        dt = current_time_abs - self.last_update_time

        if dt < WORLD_UPDATE_INTERVAL:
             return messages
        self.last_update_time = current_time_abs

        # An idle headless server does not tick until a client connects. Prime
        # cooldowns from that first real simulation tick, not process boot,
        # so a late-joining player does not trigger a synchronized crowd move.
        if not self._simulation_has_started:
            self._simulation_has_started = True
            for npc in self.npcs.values():
                cooldown = max(0.0, float(getattr(npc, "move_cooldown", 0.0)))
                phase = (sum(ord(char) for char in str(getattr(npc, "obj_id", ""))) % 1000) / 1000.0
                npc.last_moved = current_time_abs + (phase * cooldown)

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
            # An NPC update may move the NPC (for example, a combatant fleeing).
            # Its message describes the event from the room it started in, so
            # route it to observers there rather than to the destination room.
            message_location = (npc.current_region_id, npc.current_room_id)
            npc_message = npc.update(self, current_time_abs)
            if npc_message:
                messages.append((message_location, npc_message))

        if self.quest_manager:
            for player in list(self.players.values()):
                self.quest_manager.check_quest_completion(player)

        # A creature can die without anyone calling `die()`: `take_damage` clears
        # `is_alive`, and only the player's own blows went on to `die()`. So a creature
        # that burned, was poisoned or was killed by another creature was swept away with no
        # loot, no return timer for a friendly, and no event for a trigger. Find those
        # deaths, let `die()` run, and raise the event once.
        for npc in [n for n in self.npcs.values() if not n.is_alive and not getattr(n, "_death_processed", False)]:
            messages.extend(self._reap_unclaimed_death(npc))

        npcs_to_remove = [npc_id for npc_id, npc in self.npcs.items() if not npc.is_alive]
        for npc_id in npcs_to_remove: self.npcs.pop(npc_id, None)

        self.instance_manager.check_and_cleanup_completed_instances()
        
        return messages

    def _reap_unclaimed_death(self, npc: NPC) -> List[Tuple[Optional[Tuple[str, str]], str]]:
        npc.die(self)
        location = (npc.current_region_id, npc.current_room_id)
        witness = next(
            (p for p in self.players.values() if (p.current_region_id, p.current_room_id) == location), None
        )
        text = self.dispatch_event("npc_killed", {"player": witness, "npc": npc})
        return [(location, text)] if text else []

    def find_path(self, source_region_id: str, source_room_id: str, target_region_id: str, target_room_id: str) -> Optional[List[str]]:
        return find_path(self, source_region_id, source_room_id, target_region_id, target_room_id)

    def add_to_respawn_queue(self, npc: NPC):
        self.respawn_manager.add_to_queue(npc)

    def look(self, minimal: bool = False, player: Optional['Player'] = None) -> str:
        return generate_room_description(self, minimal, player=player)

    def _locked_message(self, base_message: str, key_id: Optional[str]) -> str:
        """A locked exit's default refusal, naming the required key when
        one is actually set and resolvable -- never inventing a key that
        doesn't exist (a `key_id: null` lock, e.g. a pick-only door, keeps
        the plain base message)."""
        if not key_id:
            return base_message
        template = self.item_templates.get(key_id)
        if not template:
            return base_message
        key_name = str(template.get("name", key_id))
        article = "an" if key_name[:1].lower() in "aeiou" else "a"
        return f"{base_message} It looks like it needs {article} {key_name}."

    def _attempt_combat_retreat(self, player: 'Player') -> Tuple[bool, Optional[str]]:
        """Walking away mid-fight isn't free: a contested check against the
        toughest engaged hostile. Which skill governs it, and how the
        difficulty scales, is content-authored (ruleset "combat.retreat")
        rather than assumed -- a content set may reuse the same skill it
        uses for theft (slipping away from a fight is the same act as
        slipping away with stolen goods), or name a distinct one.
        Returns (allowed_to_move, failure_message)."""
        combat_state = getattr(player.runtime_state, "combat", None)
        if combat_state is None or not combat_state.in_combat:
            return True, None
        here = (player.current_region_id, player.current_room_id)
        live_hostiles = [
            t for t in combat_state.targets
            if getattr(t, "is_alive", False) and factions.is_hostile(t, self)
            and (getattr(t, "current_region_id", None), getattr(t, "current_room_id", None)) == here   # one left behind is not holding you
        ]
        if not live_hostiles:
            return True, None
        retreat_config = self.ruleset_section("combat").get("retreat", {})
        if not isinstance(retreat_config, dict) or not retreat_config:
            return True, None
        skill = str(retreat_config.get("skill", "")).strip()
        if not skill:
            return True, None
        base_difficulty = retreat_config.get("base_difficulty", 10)
        per_level = retreat_config.get("difficulty_per_hostile_level", 2)
        difficulty = base_difficulty + per_level * max(getattr(t, "level", 1) for t in live_hostiles)
        success, _ = SkillSystem.practice_check(player, skill, difficulty)
        if not success:
            return False, f"{FORMAT_ERROR}You can't break away from the fight!{FORMAT_RESET}"
        # Deliberately not forcing exit_combat here: a hostile left behind
        # keeps remembering the fight (matching existing, intentional aggro
        # persistence -- see test_npc_aggro_persistence.py), and naturally
        # exits combat on its own next turn once it finds no same-room
        # target (engine/npcs/combat.py::try_attack). The check's only job
        # is gating whether the move is allowed to happen at all.
        return True, None

    def change_room(self, direction: str, player: Optional['Player'] = None) -> str:
        active_player = self.resolve_reference_player(player)
        if not active_player or not active_player.is_alive:
             return f"{FORMAT_ERROR}You cannot move while dead.{FORMAT_RESET}"

        old_region_id = active_player.current_region_id
        old_room_id = active_player.current_room_id
        current_room = self.get_current_room(active_player)

        if not old_region_id or not old_room_id or not current_room:
            return f"{FORMAT_ERROR}You are lost in an unknown place and cannot move.{FORMAT_RESET}"

        retreat_allowed, retreat_failure_msg = self._attempt_combat_retreat(active_player)
        if not retreat_allowed:
            return retreat_failure_msg or f"{FORMAT_ERROR}You can't break away from the fight!{FORMAT_RESET}"

        gate_refusal = self._evaluate_exit_gate(active_player, current_room, direction)
        if gate_refusal:
            return gate_refusal

        destination_id = current_room.get_exit(direction)
        if not destination_id: return f"{FORMAT_ERROR}You cannot go {direction}.{FORMAT_RESET}"

        if destination_id == HOUSE_ENTRY_SENTINEL:
            resolved_destination, failure_msg = self.housing_manager.resolve_personal_door(active_player)
            if resolved_destination is None:
                return failure_msg
            destination_id = resolved_destination

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
                  fail_msg = self._locked_message(f"The door to {target_room.name} is locked.", target_lock_key)
                  return f"{FORMAT_ERROR}{fail_msg}{FORMAT_RESET}"

        # The commit point: every check has passed, so this is the move. A key is spent
        # here and not in the gate, or a move refused for another reason (a second lock
        # behind the door) would cost one.
        spent_note = self._commit_exit_gate(active_player, current_room, direction)
        arrival = self._arrive(active_player, new_region_id, new_room_id, old_region_id)
        return f"{FORMAT_SUCCESS}{spent_note}{FORMAT_RESET}\n\n{arrival}" if spent_note else arrival

    @staticmethod
    def _exit_open_key(player: 'Player', direction: str) -> str:
        return "exit_open:%s:%s:%s" % (player.current_region_id, player.current_room_id, direction)

    def _exit_is_open_for(self, player: 'Player', direction: str) -> bool:
        flags = getattr(player, "flags", None)
        return isinstance(flags, dict) and bool(flags.get(self._exit_open_key(player, direction)))

    def _commit_exit_gate(self, player: 'Player', room: Room, direction: str) -> str:
        """Spend what a `consume` requirement takes, and remember the door is open.

        The memory is a flag on the *player* (`exit_open:<region>:<room>:<direction>`),
        never an edit to the room's requirement: a static room is rebuilt from its JSON,
        so editing the requirement would re-lock a door whose key was spent and soft-lock
        the player. It survives a save, and is per player.
        """
        dir_req = room.properties.get("exit_requirements", {}).get(direction)
        if not dir_req or not dir_req.get("consume") or self._exit_is_open_for(player, direction):
            return ""
        from engine.dialogue.effects import entry_pairs

        req_type = dir_req.get("type")
        if req_type == "locked":
            spent = [(dir_req.get("key_id"), 1)] if dir_req.get("key_id") else []
        elif req_type == "condition":
            spent = entry_pairs(dir_req.get("consume"))
        else:
            spent = []
        names = []
        for item_id, quantity in spent:
            player.inventory.remove_item(item_id, quantity)
            template = self.item_templates.get(item_id) or {}
            names.append(str(template.get("name", item_id)))
        flags = getattr(player, "flags", None)
        if not isinstance(flags, dict):
            flags = player.flags = {}
        flags[self._exit_open_key(player, direction)] = True
        what = ", ".join(names) if names else "what it asked"
        return f"You spend the {what}; the way {direction} is open to you from now on."

    # How many arrivals may chain, each sending the player on to the next, before the
    # next is refused: a loop of warps must not hang the server.
    TELEPORT_CHAIN_LIMIT = 3
    _teleport_depth = 0

    def teleport_player(self, player: 'Player', region_id: str, room_id: str) -> Tuple[bool, str]:
        """Put `player` in a room without walking there.

        Arrives through `_arrive` (visited, location, quest room entry, what they see) and
        never asks the exit gate: a warp does not pass through a door, so a lock on the
        way in does not stop it. Returns `(True, what the player reads)`, or
        `(False, "no_room" | "too_deep" | "dead")`.
        """
        if player is None or not getattr(player, "is_alive", False):
            return False, "dead"
        region = self.get_region(region_id)
        if region is None or region.get_room(room_id) is None:
            return False, "no_room"
        if self._teleport_depth >= self.TELEPORT_CHAIN_LIMIT:
            return False, "too_deep"
        self._teleport_depth += 1
        try:
            return True, self._arrive(player, region_id, room_id, player.current_region_id)
        finally:
            self._teleport_depth -= 1

    def _evaluate_exit_gate(self, player: 'Player', room: Room, direction: str) -> Optional[str]:
        """Whether the way `direction` from `room` is open to `player`.

        Returns the refusal, already formatted for the player, or None when the way is
        open. Movement, and anything else that asks "may this player go that way", goes
        through here, so a new kind of requirement is written once.
        """
        dir_req = room.properties.get("exit_requirements", {}).get(direction)
        if not dir_req:
            return None
        if dir_req.get("consume") and self._exit_is_open_for(player, direction):
            return None   # a door this player has already spent a key on
        req_type = dir_req.get("type")
        if req_type == "skill":
            skill = dir_req.get("skill_name")
            difficulty = dir_req.get("difficulty", 10)
            fail_msg = dir_req.get("failure_message", "You fail to traverse the path.")

            success, roll_msg = SkillSystem.practice_check(player, skill, difficulty)
            if not success:
                return f"{FORMAT_ERROR}{fail_msg}{FORMAT_RESET} (Requires {skill} {difficulty}+)"

        elif req_type == "locked":
            key_id = dir_req.get("key_id")
            has_key = any(slot.item and slot.item.obj_id == key_id for slot in player.inventory.slots)
            if not has_key:
                fail_msg = dir_req.get("failure_message") or self._locked_message(f"The way {direction} is locked.", key_id)
                return f"{FORMAT_ERROR}{fail_msg}{FORMAT_RESET}"

        elif req_type == "condition":
            # Read afresh every time, so a condition that stopped holding shuts the way
            # again; an unknown kind fails closed (`conditions.evaluate`).
            from engine import conditions

            evaluation = conditions.evaluate(dir_req.get("condition"), player)
            if not evaluation.satisfied:
                reason = evaluation.reasons[0] if evaluation.reasons else "the requirements are not met yet"
                fail_msg = dir_req.get("failure_message") or f"The way {direction} is closed to you: {reason}."
                return f"{FORMAT_ERROR}{fail_msg}{FORMAT_RESET}"
        return None

    def _arrive(self, active_player: 'Player', new_region_id: str, new_room_id: str, old_region_id: Optional[str]) -> str:
        """Put `active_player` in a room and everything that follows from being there.

        Marks it visited, sets the location, tells the quest manager, flags an instance
        quest, and returns the text the player reads: the region banner, the room, the
        travel note, first-arrival notes, then quest updates. The gate has already been
        passed (or does not apply, as for a teleport); this does not ask again.
        """
        target_region = self.get_region(new_region_id)
        target_room = target_region.get_room(new_room_id)
        target_room.visited = True
        came_from = (active_player.current_region_id, active_player.current_room_id)
        active_player.current_region_id = new_region_id
        active_player.current_room_id = new_room_id
        if hasattr(active_player, "drop_distant_targets"):
            active_player.drop_distant_targets()   # a fight left behind is over for you
        from engine.dialogue import runner as dialogue_runner
        dialogue_runner.release_on_departure(self, active_player)   # you cannot go on talking to someone you left
        from engine.npcs import companions
        companion_lines = companions.travel_with(self, active_player, *came_from)

        # NEW: Get quest updates (returns list of strings instead of printing)
        quest_updates = []
        if self.quest_manager:
            quest_updates = self.quest_manager.handle_room_entry(active_player)

        if new_region_id.startswith("instance_") and active_player.runtime_state.quests is not None:
            for quest in active_player.runtime_state.quests.active.values():
                if quest.get("instance_region_id") == new_region_id:
                    quest["completion_check_enabled"] = True
                    break

        # Triggers run here, after the location is set and before the room is described,
        # so an exit a trigger reveals or seals is what `look` then lists.
        trigger_lines = self.trigger_runner.fire_on_enter(active_player, new_region_id, new_room_id)

        region_change_msg = f"{FORMAT_HIGHLIGHT}You have entered {target_region.name}.{FORMAT_RESET}\n\n" if new_region_id != old_region_id else ""
        
        # Assemble Final Output
        output = region_change_msg + self.look(minimal=True, player=active_player)

        weather_manager = getattr(getattr(self, "game", None), "weather_manager", None)
        travel_note = weather_manager.travel_note(target_region, target_room) if weather_manager else ""
        if travel_note:
            output += "\n\n" + travel_note

        if companion_lines:
            output += "\n\n" + "\n".join(companion_lines)

        if trigger_lines:
            output += "\n\n" + "\n\n".join(trigger_lines)

        # First arrival somewhere new is worth something, so the world itself is
        # the progress curve (ROADMAP P4). Region and landmark entries pay once;
        # a repeat visit is silent.
        arrival_notes = []
        region_note = advancement.award(
            active_player, advancement.KIND_REGION, new_region_id,
            payload={"region_id": new_region_id},
        )
        if region_note:
            arrival_notes.append(region_note)
        landmark_note = advancement.award(
            active_player, advancement.KIND_LANDMARK,
            "%s:%s" % (new_region_id, new_room_id),
            payload={"region_id": new_region_id, "room_id": new_room_id},
        )
        if landmark_note:
            arrival_notes.append(landmark_note)
        if arrival_notes:
            output += "\n\n" + "\n".join(arrival_notes)

        # Append quest updates at the bottom so they are seen last
        if quest_updates:
            output += "\n\n" + "\n\n".join(quest_updates)

        return output

    def dispatch_event(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        if event_type == "npc_killed" and data.get("witness"):
            # A player saw it happen and did nothing: the story's triggers hear of it, and nothing is credited or
            # charged to them (no quest progress, no reputation, no encounter record).
            lines = self.trigger_runner.fire_npc_killed(data.get("player"), data.get("npc")) if data.get("npc") is not None else []
            return "\n\n".join(line for line in lines if line) or None
        if event_type == "npc_killed":
            quest_msg = self.quest_manager.handle_npc_killed(event_type, data) if self.quest_manager else None
            rep_msg = self._handle_reputation_on_kill(data)

            # Meeting a kind of creature for the first time is recorded once, so
            # the ledger reflects what a player has encountered rather than how
            # much they have ground. Keyed by template, not instance.
            player = data.get("player")
            npc = data.get("npc")
            encounter_msg = ""
            if player is not None and npc is not None:
                template_id = str(getattr(npc, "template_id", "") or getattr(npc, "name", "") or "")
                encounter_msg = advancement.award(
                    player, advancement.KIND_CREATURE, template_id,
                    payload=advancement.npc_payload(npc),
                )

            trigger_lines = self.trigger_runner.fire_npc_killed(player, npc) if npc is not None else []
            # What happened comes first (a scene's own text), then what it means for the quest, then
            # the side notices; each is a paragraph of its own.
            parts = [m for m in (*trigger_lines, quest_msg, rep_msg, encounter_msg) if m]
            return "\n\n".join(parts) if parts else None
        return None

    def _handle_reputation_on_kill(self, data: Dict[str, Any]) -> Optional[str]:
        player = data.get("player")
        npc = data.get("npc")
        if not player or not npc: return None
        
        faction = npc.faction
        if factions.is_hostile(npc, self):
            player.adjust_reputation("friendly", REP_KILL_REWARD_HOSTILE)
            return None 
        elif factions.is_friendly(npc, self) or factions.disposition_of(npc, self) == "neutral":
            player.adjust_reputation("friendly", REP_KILL_PENALTY_SAME_FACTION)
            player.adjust_reputation("neutral", REP_KILL_PENALTY_SAME_FACTION)
            return f"{FORMAT_ERROR}Your reputation plummets! You are now looked upon with suspicion.{FORMAT_RESET}"
        return None

    def attempt_pick_lock_direction(self, direction: str, player: Optional['Player'] = None) -> str:
        active_player = self.resolve_reference_player(player)
        current_room = self.get_current_room(active_player)
        if not current_room: return "You are nowhere."

        lockpicking_skill = str(self.ruleset_section("locksmithing").get("skill", "")).strip()
        if not lockpicking_skill:
            return "There is no way to pick a lock in this world."

        custody = self.ruleset_section("crime").get("custody", {})
        room_property = str(custody.get("room_property", "")).strip() if isinstance(custody, dict) else ""
        escape_alert_margin = custody.get("escape_alert_margin", 0) if isinstance(custody, dict) else 0
        escape_sentence_penalty = custody.get("escape_sentence_penalty_seconds", 0) if isinstance(custody, dict) else 0

        reqs = current_room.properties.get("exit_requirements", {})
        dir_req = reqs.get(direction)

        if dir_req and dir_req.get("type") == "locked":
            difficulty = dir_req.get("pick_difficulty", 999)
            if difficulty > 100: return "This lock cannot be picked."

            lockpick_item = None
            if not active_player: return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
            for slot in active_player.inventory.slots:
                if isinstance(slot.item, Lockpick):
                    lockpick_item = slot.item
                    break

            if not lockpick_item:
                return "You need a lockpick."

            success, msg, margin = SkillSystem.attempt_check_with_margin(active_player, lockpicking_skill, difficulty)
            is_jail_cell = bool(room_property) and bool(current_room.properties.get(room_property))
            if success:
                del reqs[direction]
                current_room.update_property("exit_requirements", reqs)
                SkillSystem.grant_xp(active_player, lockpicking_skill, difficulty)
                escape_note = ""
                if is_jail_cell and active_player.jailed_until is not None:
                    self.crime_manager.forfeit_confiscated_items(active_player)
                    escape_note = " Whatever the guards confiscated stays with them now."
                return f"{FORMAT_SUCCESS}Click! You unlock the way {direction}.{escape_note}{FORMAT_RESET}"
            else:
                wear_msg = lockpick_item.apply_wear(active_player, margin) or ""
                alert_note = ""
                if is_jail_cell and active_player.jailed_until is not None and abs(margin) >= escape_alert_margin:
                    active_player.jailed_until += escape_sentence_penalty
                    alert_note = " The noise brings a guard running -- your sentence just got longer."
                return f"{FORMAT_ERROR}You fail to pick the lock.{alert_note}{FORMAT_RESET}{wear_msg}"

        dest_id = current_room.get_exit(direction)
        if dest_id:
            rid = getattr(active_player, "current_region_id", None)
            if ":" in dest_id: rid, dest_id = dest_id.split(":")

            reg = self.get_region(rid) if rid else None
            if reg:
                room = reg.get_room(dest_id)
                if room and room.get_property("locked_by"):
                    difficulty = 20

                    lockpick_item = None
                    if not active_player: return f"{FORMAT_ERROR}Player not found.{FORMAT_RESET}"
                    for slot in active_player.inventory.slots:
                        if isinstance(slot.item, Lockpick):
                            lockpick_item = slot.item
                            break

                    if not lockpick_item: return "You need a lockpick."
                    success, msg, margin = SkillSystem.attempt_check_with_margin(active_player, lockpicking_skill, difficulty)
                    if success:
                        room.properties["locked_by"] = None
                        SkillSystem.grant_xp(active_player, lockpicking_skill, 10)
                        return f"{FORMAT_SUCCESS}Click! You unlock the door to {room.name}.{FORMAT_RESET}"
                    else:
                        wear_msg = lockpick_item.apply_wear(active_player, margin) or ""
                        return f"{FORMAT_ERROR}You fail to pick the lock.{FORMAT_RESET}{wear_msg}"

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

    def notify_player(self, player: Any, text: str) -> None:
        self.pending_player_notices.append((player, text))

    def schedule(self, delay: float, action: Any, key: Optional[str] = None) -> None:
        """Run `action()` about `delay` seconds from now (on the world clock), from the server's tick.
        `key` names what it belongs to, so the owner can ask whether any of it is still pending."""
        self.scheduled_actions.append((float(self.clock.now()) + max(0.0, float(delay)), action, key))

    def is_scheduled(self, key: str) -> bool:
        return any(entry[2] == key for entry in self.scheduled_actions)

    def run_scheduled(self) -> None:
        """Run what has come due, oldest first. One that fails is dropped, not retried."""
        now = float(self.clock.now())
        due = sorted((entry for entry in self.scheduled_actions if entry[0] <= now), key=lambda entry: entry[0])
        if not due:
            return
        self.scheduled_actions = [entry for entry in self.scheduled_actions if entry[0] > now]
        for _when, action, _key in due:
            try:
                action()
            except Exception as error:  # noqa: BLE001 - a broken beat must not stop the world tick
                Logger.error("World", f"a scheduled action failed: {error}")

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
        npc.last_moved = self.clock.now()
        npc.world = self
        self.npcs[npc.obj_id] = npc
    
    def get_npc(self, instance_id: str) -> Optional[NPC]: return self.npcs.get(instance_id)

    def spawn_npc(
        self, template_id: str, region_id: str, room_id: str, instance_id: Optional[str] = None
    ) -> Tuple[Optional[NPC], str]:
        """Place a new NPC from a template, calling that room home.

        Returns `(npc, "spawned")`; `(existing, "present")` when an NPC with that id is
        already alive, so asking twice never makes two (the default id is the placement
        pattern, `<template>_at_<room>`); or `(None, "no_template" | "no_room")`.
        """
        if template_id not in self.npc_templates:
            return None, "no_template"
        region = self.get_region(region_id)
        if region is None or region.get_room(room_id) is None:
            return None, "no_room"
        instance_id = instance_id or f"{template_id}_at_{room_id}"
        existing = self.npcs.get(instance_id)
        if existing is not None and existing.is_alive:
            return existing, "present"
        npc = NPCFactory.create_npc_from_template(
            template_id, self, instance_id,
            current_region_id=region_id, current_room_id=room_id,
            home_region_id=region_id, home_room_id=room_id,
        )
        if npc is None:
            return None, "no_template"
        self.add_npc(npc)
        return npc, "spawned"

    def remove_npcs(
        self, identifier: str, region_id: Optional[str] = None, room_id: Optional[str] = None
    ) -> Tuple[List[NPC], int]:
        """Take NPCs out of the world without their dying: no loot, no respawn timer, no
        kill credit, because nothing was killed. `identifier` is an instance id or a
        template id; a region and room narrow it to those standing there.

        A creature of that kind that was killed earlier and is waiting to return is
        cancelled too, or "the hermit vanishes" would end with the hermit walking back in.
        Returns `(the NPCs removed, the pending returns cancelled)`.
        """
        removed: List[NPC] = []
        for npc in list(self.npcs.values()):
            if not npc.is_alive or identifier not in (npc.obj_id, npc.template_id):
                continue
            if region_id is not None and (npc.current_region_id, npc.current_room_id) != (region_id, room_id):
                continue
            if npc.properties.get("is_summoned"):
                npc.despawn(self, silent=True)   # let go of its owner's ledger first
            npc.is_alive = False
            self.npcs.pop(npc.obj_id, None)
            removed.append(npc)

        queue = self.respawn_manager.respawn_queue
        kept = [
            entry for entry in queue
            if not (identifier in (entry.get("template_id"), entry.get("instance_id"))
                    and (region_id is None or (entry.get("home_region_id"), entry.get("home_room_id")) == (region_id, room_id)))
        ]
        cancelled = len(queue) - len(kept)
        if cancelled:
            self.respawn_manager.respawn_queue = kept
        return removed, cancelled
    
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
        # Through the same room -> district -> region chain as the atmosphere
        # properties, so a room (or district) can depart from its region. The
        # room id used to be taken and ignored: a hostile placed in a room
        # authored `"safe_zone": false` inside a safe region never attacked.
        return bool(self.get_env_property(region_id, room_id, "safe_zone", False))
    
    def get_district(self, region_id: Optional[str], room_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return the district (a plain dict, content-authored on the
        region's `properties.districts`) a room belongs to, or None. Its
        member room list is authored under "members" -- "rooms" is
        accepted too for older/hand-authored data that used that key.

        A content set that turns on `ruleset.world.regions.enforce_district_
        coverage` never gets None back for a real room: any room an author
        left out of every district resolves to a synthetic, hidden catch-all
        instead, so every room always has *some* district to read ambient
        properties from (see `get_env_property`) and callers don't need a
        None-means-no-district special case. Content sets that leave the
        policy off keep exactly today's behaviour.
        """
        if not region_id or not room_id:
            return None
        region = self.get_region(region_id)
        if not region:
            return None
        districts = region.properties.get("districts", {})
        if not isinstance(districts, dict):
            districts = {}
        for district in districts.values():
            if not isinstance(district, dict):
                continue
            members = district.get("members", district.get("rooms", []))
            if room_id in members:
                return district
        if room_id not in region.rooms:
            return None
        regions_policy = self.ruleset_section("world").get("regions", {})
        if not isinstance(regions_policy, dict) or not regions_policy.get("enforce_district_coverage", False):
            return None
        return self._hidden_district_for(region_id)

    def _hidden_district_for(self, region_id: str) -> Dict[str, Any]:
        """The lazily-built, cached catch-all district for a region under
        `enforce_district_coverage`. Never shown to a player -- callers that
        display a district (e.g. the room header) must skip one whose
        `hidden` flag is set -- and carries no authored properties of its
        own, so `get_env_property` falls through it to the region exactly as
        it would fall through a real None.
        """
        cached = self._hidden_districts.get(region_id)
        if cached is not None:
            return cached
        region = self.get_region(region_id)
        covered: set = set()
        districts = region.properties.get("districts", {}) if region else {}
        if isinstance(districts, dict):
            for district in districts.values():
                if isinstance(district, dict):
                    covered.update(str(member_id) for member_id in district.get("members", district.get("rooms", [])))
        members = [room_id for room_id in region.rooms.keys() if room_id not in covered] if region else []
        hidden_district = {
            "name": region.name if region else region_id,
            "kind": "unassigned",
            "hidden": True,
            "members": members,
        }
        self._hidden_districts[region_id] = hidden_district
        return hidden_district

    def get_env_property(self, region_id: Optional[str], room_id: Optional[str], key: str, default: Any = None) -> Any:
        """Resolve an environmental/atmospheric property (dark, outdoors,
        noisy, smell, temperature, ...) through a room -> district -> region
        deviation chain: a room only needs to author a value when it departs
        from its district's norm, and a district only needs one when it
        departs from its region's -- the first tier that actually sets the
        key wins, and an unset key at every tier falls back to `default`.

        Districts and regions store these the same flat way a room does
        (a plain key alongside their other authored fields / properties),
        so content that already knows how to set "dark": true on a region's
        GLOBAL PROPERTIES or a district needs no new authoring concept.
        """
        region = self.get_region(region_id) if region_id else None
        if not region:
            return default

        if room_id:
            room = region.get_room(room_id)
            if room is not None:
                room_setting = room.get_property(key)
                if room_setting is not None:
                    return room_setting

        district = self.get_district(region_id, room_id)
        if district is not None:
            district_setting = district.get(key)
            if district_setting is not None:
                return district_setting

        region_setting = region.get_property(key)
        if region_setting is not None:
            return region_setting
        return default

    def is_location_outdoors(self, region_id: str, room_id: str) -> bool:
        return self.get_env_property(region_id, room_id, "outdoors", True)
    
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
         return resolve_best(name, self.get_current_room_npcs(player))

    def find_npc_in_room_for_player(self, name: str, player: Optional['Player']) -> Optional[NPC]:
         return resolve_best(name, self.get_npcs_for_player(player))
    
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
            for room_id in region.rooms.keys():
                if self.is_location_safe(region_id, room_id):
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
