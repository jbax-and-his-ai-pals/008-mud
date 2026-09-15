import os
import random
from typing import Dict, Any, List, Optional, TYPE_CHECKING, cast

from engine.config import (
    QUEST_SYSTEM_CONFIG, QUEST_TYPES_ALL, MAX_QUESTS_ON_BOARD, FORMAT_HIGHLIGHT, FORMAT_RESET
)
from engine.core.quest_generation.generator import QuestGenerator
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.social.relationships import apply_relationship_milestones, relationship_key
from engine.utils.logger import Logger
from .loader import load_quest_templates
from .tracker import check_quest_completion, handle_npc_killed, handle_item_crafted, handle_resource_gathered

if TYPE_CHECKING:
    from engine.world.world import World
    from engine.npcs.npc import NPC

class QuestManager:
    def __init__(self, world: 'World'):
        self.world = world
        self.content_root = world.content_root
        self.config = {**QUEST_SYSTEM_CONFIG, **world.ruleset_section("quest_generation")}
        self.config.setdefault(
            "quest_board_locations",
            [f"{world.content_set.start_region_id}:{world.content_set.start_room_id}"],
        )
        self.npc_interests: Dict[str, List[str]] = {}
        self.quest_templates: Dict[str, Any] = load_quest_templates(self.content_root)
        
        self.generator = QuestGenerator(world, cast('QuestManager', self))
        
        self._load_npc_interests()

    def _load_npc_interests(self):
        if not self.world or not hasattr(self.world, 'npc_templates'): return
        config_interests = self.config.get("npc_quest_interests", {})
        for template_id, template_data in self.world.npc_templates.items():
            if not isinstance(template_data, dict): continue
            interests = template_data.get("properties", {}).get("quest_interests")
            if interests is None: interests = config_interests.get(template_id)
            if isinstance(interests, list): self.npc_interests[template_id] = [str(i) for i in interests if isinstance(i, str)]

    def resolve_turn_in_name(self, quest_data: Dict[str, Any]) -> str:
        """Helper to get the display name of the turn-in target."""
        stages = quest_data.get("stages", [])
        idx = quest_data.get("current_stage_index", 0)
        giver_id = "unknown"
        
        if stages and idx < len(stages):
            giver_id = stages[idx].get("turn_in_id")
        
        if not giver_id:
             giver_id = quest_data.get("giver_instance_id")
        
        if not isinstance(giver_id, str):
            return "the quest giver"
            
        giver = self.world.get_npc(giver_id)
        if giver: return giver.name
        if giver_id == "quest_board": return self.world.quest_board_name()
        
        if giver_id in self.world.npc_templates:
             return self.world.npc_templates[giver_id].get("name", "Quest Giver")
        return "the quest giver"

    def get_active_objective(self, quest_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        objectives = self.get_active_objectives(quest_data)
        return objectives[0] if objectives else None

    def get_active_objectives(self, quest_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the current stage's acceptable objective routes.

        ``objective`` remains the compact authoring path.  A stage may instead
        (or additionally) author ``objectives_any`` to let one completed route
        satisfy the stage.  The engine interprets only objective mechanics;
        content decides what those routes mean.
        """
        stages = quest_data.get("stages", [])
        idx = quest_data.get("current_stage_index", 0)
        if not isinstance(stages, list) or not (0 <= idx < len(stages)) or not isinstance(stages[idx], dict):
            return []
        stage = stages[idx]
        routes: List[Dict[str, Any]] = []
        primary = stage.get("objective")
        if isinstance(primary, dict):
            routes.append(primary)
        alternatives = stage.get("objectives_any", [])
        if isinstance(alternatives, list):
            routes.extend(route for route in alternatives if isinstance(route, dict))
        return routes

    def _resolve_reference_player(self, player=None):
        if not self.world:
            return None
        return self.world.resolve_reference_player(player)

    def ensure_initial_quests(self, player=None):
        if not self.world:
            return
        player = self._resolve_reference_player(player)
        if player is None:
            return
        current_quests = self.world.quest_board
        self._add_authored_board_quests(current_quests, player)
        slots_to_fill = max(0, MAX_QUESTS_ON_BOARD - len(current_quests))
        if slots_to_fill == 0: return

        possible_types = QUEST_TYPES_ALL
        player_level = player.runtime_state.progression.level if player.runtime_state.progression is not None else 1

        while slots_to_fill > 0:
            quest_type = random.choice(possible_types)
            new_quest = None

            if quest_type == "instance":
                new_quest = self.generator.generate_instance_quest(player_level)
            else:
                new_quest = self.generator.generate_noninstance_quest(player_level, quest_type)
            
            if new_quest:
                current_quests.append(new_quest)
                slots_to_fill -= 1
            else:
                break 

    def _add_authored_board_quests(
        self,
        board: List[Dict[str, Any]],
        player,
        only_template_ids: Optional[set[str]] = None,
    ) -> None:
        """Seed opt-in, content-authored notices before procedural board fill.

        Content sets may declare ``quest_generation.authored_board_templates``.
        Each entry names a normal quest template and may name its giver by
        template id. The engine resolves the current NPC instance, but neither
        quest titles nor NPC identities are encoded here.
        """
        configured = self.config.get("authored_board_templates", [])
        if not isinstance(configured, list):
            return
        existing_template_ids = {str(quest.get("template_id", "")) for quest in board}
        player_level = player.runtime_state.progression.level if player.runtime_state.progression is not None else 1
        for entry in configured:
            if not isinstance(entry, dict):
                continue
            template_id = str(entry.get("template_id", "")).strip()
            if only_template_ids is not None and template_id not in only_template_ids:
                continue
            if not template_id or template_id in existing_template_ids:
                continue
            if not self.authored_board_entry_available(player, entry)[0]:
                continue
            template = self.quest_templates.get(template_id)
            if not isinstance(template, dict):
                Logger.warning("QuestManager", f"Authored board quest template '{template_id}' is missing.")
                continue
            quest = self.generator.instantiate_quest(template, player_level)
            if not isinstance(quest, dict):
                continue
            import uuid
            quest["template_id"] = template_id
            quest["instance_id"] = f"{template_id}_{uuid.uuid4().hex[:8]}"
            quest["state"] = "available"
            quest["current_stage_index"] = 0
            giver_template_id = str(entry.get("giver_template_id", "")).strip()
            if giver_template_id:
                giver = next(
                    (npc for npc in self.world.npcs.values() if getattr(npc, "template_id", None) == giver_template_id),
                    None,
                )
                if giver is not None:
                    quest["giver_instance_id"] = giver.obj_id
                quest["relationship_npc_id"] = giver_template_id
            if "relationship_min" in entry:
                # Content-set validation constrains this field; normalize it
                # here so every downstream quest consumer sees one stable
                # runtime type.
                quest["relationship_min"] = max(0, int(entry["relationship_min"]))
            board.append(quest)
            existing_template_ids.add(template_id)

    def refresh_repeatable_board_tasks(self, player=None) -> None:
        """Repost only a completed board notice whose hidden delay has passed.

        This deliberately does *not* call ``ensure_initial_quests``.  A board
        that authors no current work must still be allowed to say it is empty;
        reading it should not manufacture procedural tasks.  Normal board
        replenishment continues to happen on acceptance and completion.
        """
        player = self._resolve_reference_player(player)
        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        available_at = getattr(quests, "repeatable_available_at", {}) if quests is not None else {}
        if not isinstance(available_at, dict) or not available_at:
            return
        ready_template_ids: set[str] = set()
        for template_id in available_at:
            entry = self._authored_board_entry(str(template_id))
            if entry is not None and self.authored_board_entry_available(player, entry)[0]:
                ready_template_ids.add(str(template_id))
        if ready_template_ids:
            self._add_authored_board_quests(self.world.quest_board, player, ready_template_ids)

    def _authored_board_entry(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Return the board configuration that owns an authored template.

        Board policy belongs in the ruleset rather than in a quest definition:
        the same quest can be a one-off story reward in one content set and a
        recurring notice in another.
        """
        configured = self.config.get("authored_board_templates", [])
        if not isinstance(configured, list):
            return None
        for entry in configured:
            if isinstance(entry, dict) and str(entry.get("template_id", "")).strip() == template_id:
                return entry
        return None

    @staticmethod
    def _repeatable_policy(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        policy = entry.get("repeatable")
        return policy if isinstance(policy, dict) else None

    @staticmethod
    def _quest_uses_template(quest_data: Any, template_id: str) -> bool:
        return isinstance(quest_data, dict) and str(quest_data.get("template_id", "")) == template_id

    def _player_has_active_template(self, player, template_id: str) -> bool:
        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        active = getattr(quests, "active", {}) if quests is not None else {}
        return any(self._quest_uses_template(quest, template_id) for quest in active.values())

    def _player_has_completed_template(self, player, template_id: str) -> bool:
        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        if quests is None:
            return False
        completed = {
            **(getattr(quests, "completed", {}) or {}),
            **(getattr(quests, "archived", {}) or {}),
        }
        return any(self._quest_uses_template(quest, template_id) for quest in completed.values())

    def _world_now(self) -> float:
        clock = getattr(self.world, "clock", None)
        if clock is not None and hasattr(clock, "now"):
            return float(clock.now())
        return 0.0

    def authored_board_entry_available(self, player, entry: Dict[str, Any]) -> tuple[bool, str]:
        """Whether this player may take an authored board task right now.

        The delay is intentionally internal.  Content authors provide a short
        in-world explanation, never a number of seconds or a countdown, so a
        board feels attended rather than like a vending machine.  Availability
        is per player and stored with their quest state, which makes the rule
        correct after a save/load and fair in a shared world.
        """
        template_id = str(entry.get("template_id", "")).strip()
        if not template_id:
            return True, ""
        # Command rendering receives an instantiated board notice, while
        # seeding receives the ruleset entry itself.  Resolve the canonical
        # ruleset entry in both cases so procedural quests are untouched.
        configured_entry = self._authored_board_entry(template_id)
        if configured_entry is None:
            return True, ""
        policy = self._repeatable_policy(configured_entry)
        notice = str((policy or {}).get("unavailable_text", "")).strip()

        if self._player_has_active_template(player, template_id):
            return False, notice
        if policy is None:
            return (not self._player_has_completed_template(player, template_id)), ""

        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        available_at = getattr(quests, "repeatable_available_at", {}).get(template_id, 0.0) if quests is not None else 0.0
        try:
            is_ready = float(available_at) <= self._world_now()
        except (TypeError, ValueError):
            is_ready = True
        return is_ready, ("" if is_ready else notice)

    def authored_board_unavailable_notices(self, player) -> List[str]:
        """Distinct diegetic explanations for board tasks currently resting."""
        configured = self.config.get("authored_board_templates", [])
        if not isinstance(configured, list):
            return []
        notices: List[str] = []
        for entry in configured:
            if not isinstance(entry, dict) or self._repeatable_policy(entry) is None:
                continue
            available, notice = self.authored_board_entry_available(player, entry)
            if not available and notice and notice not in notices:
                notices.append(notice)
        return notices

    def _record_repeatable_board_completion(self, player, quest_data: Dict[str, Any]) -> None:
        """Start a hidden re-post delay after an explicitly repeatable task."""
        template_id = str(quest_data.get("template_id", "")).strip()
        entry = self._authored_board_entry(template_id)
        if entry is None:
            return
        policy = self._repeatable_policy(entry)
        if policy is None:
            return
        try:
            delay_seconds = max(0.0, float(policy.get("delay_seconds", 0.0)))
        except (TypeError, ValueError):
            delay_seconds = 0.0
        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        if quests is not None:
            quests.repeatable_available_at[template_id] = self._world_now() + delay_seconds

    def replenish_board(self, completed_quest_instance_id: Optional[str], player=None):
        if not self.world:
            return
        if completed_quest_instance_id:
            self.world.quest_board = [q for q in self.world.quest_board if q.get("instance_id") != completed_quest_instance_id]
        self.ensure_initial_quests(player)

    def start_quest(self, template_id: str, player, campaign_context: Optional[Dict[str, str]] = None) -> bool:
        if template_id not in self.quest_templates: 
            return False
            
        template = self.quest_templates[template_id]
        player_level = player.runtime_state.progression.level if player.runtime_state.progression is not None else 1
        quest_data = self.generator.instantiate_quest(template, player_level)
        
        import uuid
        instance_id = f"{template_id}_{uuid.uuid4().hex[:4]}"
        quest_data["instance_id"] = instance_id
        quest_data["state"] = "active"
        quest_data["current_stage_index"] = 0
        
        if campaign_context:
            quest_data["campaign_context"] = campaign_context
        
        if "giver_instance_id" not in quest_data:
            quest_data["giver_instance_id"] = "event"

        player.runtime_state.quests.active[instance_id] = quest_data
        
        # Initialize stage 0 spawns if any
        if quest_data.get("stages"):
             self._setup_stage_mechanics(quest_data, quest_data["stages"][0])

        # Check immediately if we are already satisfying a scout objective
        updates = self.handle_room_entry(player)
        if updates and self.world.game:
            for msg in updates:
                self.world.game.renderer.add_message(msg)

        server = getattr(self.world, "server", None)
        if server is not None and hasattr(server, "mirror_party_quest_acceptance"):
            for event in server.mirror_party_quest_acceptance(player, [instance_id]):
                if hasattr(server, "pending_broadcasts"):
                    server.pending_broadcasts.append(event)

        return True

    def start_campaign(self, campaign_id: str, player) -> bool:
        if self.world.campaign_manager:
            return self.world.campaign_manager.start_campaign(campaign_id, player)
        return False

    def complete_quest(self, player, quest_id: str, resolution: str = "SUCCESS") -> str:
        if quest_id not in player.runtime_state.quests.active: return ""
        
        quest_data = player.runtime_state.quests.active.pop(quest_id)
        quest_data["state"] = "completed"

        self._record_repeatable_board_completion(player, quest_data)
        
        reward_text = self._grant_rewards(player, quest_data.get("rewards", {}))
        
        if self.world.instance_manager:
            self.world.instance_manager.cleanup_quest_region(quest_id)
        
        player.runtime_state.quests.completed[quest_id] = quest_data
        
        if "campaign_context" not in quest_data:
             self.replenish_board(quest_id, player)
        
        campaign_update_msg = ""
        campaign_context = quest_data.get("campaign_context")
        if campaign_context and self.world.campaign_manager:
            c_id = campaign_context.get("campaign_id")
            n_id = campaign_context.get("node_id")
            if c_id and n_id:
                campaign_update_msg = self.world.campaign_manager.handle_quest_completion(c_id, n_id, resolution, player)
        
        full_msg = reward_text
        if campaign_update_msg:
            full_msg += "\n" + campaign_update_msg

        # Completing a quest is a recognised activity; the ledger records it
        # once per quest *template* so a repeatable board task does not pay
        # advancement XP forever (ROADMAP P4).
        from engine.core import advancement
        template_id = str(quest_data.get("template_id", "") or quest_id)
        quest_note = advancement.award(
            player, advancement.KIND_QUEST, template_id, payload={"quest_id": template_id}
        )
        if quest_note:
            full_msg += "\n" + quest_note

        server = getattr(self.world, "server", None)
        if server is not None and hasattr(server, "sync_party_quest_completion"):
            for event in server.sync_party_quest_completion(player, quest_data):
                if hasattr(server, "pending_broadcasts"):
                    server.pending_broadcasts.append(event)
        return full_msg

    def _grant_rewards(self, player, rewards) -> str:
        server = getattr(self.world, "server", None)
        if server is not None and hasattr(server, "grant_party_rewards"):
            return server.grant_party_rewards(player, rewards)

        msgs = []
        xp = rewards.get("xp", 0); gold = rewards.get("gold", 0)
        if xp > 0 and player.runtime_state.progression is not None:
            _, msg = player.gain_experience(xp); msgs.append(f"{xp} XP")
        if gold > 0 and player.runtime_state.gold is not None:
            player.runtime_state.gold += gold; msgs.append(f"{gold} {self.world.currency_name().capitalize()}")
        if "items" in rewards:
            for d in rewards["items"]:
                it = ItemFactory.create_item_from_template(d["item_id"], player.world)
                if it: player.inventory.add_item(it, d["quantity"]); msgs.append(f"{d['quantity']}x {it.name}")
        if "generated_item_data" in rewards:
            it = ItemFactory.from_dict(rewards["generated_item_data"], player.world)
            if it: player.inventory.add_item(it); msgs.append(f"{it.name}")
        relationship_rewards = rewards.get("relationships", [])
        if isinstance(relationship_rewards, list):
            for reward in relationship_rewards:
                if not isinstance(reward, dict):
                    continue
                template_id = str(reward.get("npc_template_id", "")).strip()
                try:
                    amount = int(reward.get("amount", 0))
                except (TypeError, ValueError):
                    continue
                npc = next(
                    (candidate for candidate in self.world.npcs.values() if getattr(candidate, "template_id", None) == template_id),
                    None,
                )
                if npc is None or amount == 0:
                    continue
                key = relationship_key(npc)
                old_score = int(player.npc_relationships.get(key, 0))
                new_score = max(0, min(100, old_score + amount))
                player.npc_relationships[key] = new_score
                signed_amount = f"+{amount}" if amount > 0 else str(amount)
                msgs.append(f"{signed_amount} relationship with {npc.name}")
                milestone_note = apply_relationship_milestones(player, npc, old_score, new_score, self.world)
                if milestone_note:
                    msgs.append(milestone_note)
        if not msgs: return ""
        return "Rewards: " + ", ".join(msgs)

    def advance_quest_stage(self, player, quest_id: str, choice_id: Optional[str] = None) -> Optional[str]:
        if quest_id not in player.runtime_state.quests.active: return None
        quest = player.runtime_state.quests.active[quest_id]
        
        current_index = quest.get("current_stage_index", 0)
        stages = quest.get("stages", [])
        
        if current_index >= len(stages): return "QUEST_COMPLETE"
            
        current_stage = stages[current_index]
        completion_text = current_stage.get("completion_dialogue", "Stage complete.")
        
        next_index = current_index + 1
        
        objective = current_stage.get("objective", {})
        if (objective.get("type") in ["dialogue_choice", "negotiate"]) and choice_id:
             choices = objective.get("choices", {})
             if choice_id in choices:
                 branch = choices[choice_id]
                 if branch.get("complete"):
                     # An outcome that ends the quest outright. Content needs
                     # this: without it the only way to say "and that finishes
                     # it" was `next_stage` past the end, and *forgetting* to
                     # say anything silently advanced to the next stage -- which
                     # for a negotiation whose next stage is "kill him" turned a
                     # successful truce into an order to commit murder, and made
                     # the campaign's PEACEFUL_SUCCESS branch unreachable.
                     return "QUEST_COMPLETE"
                 next_index = branch.get("next_stage", next_index)
                 completion_text = branch.get("description", completion_text)

        if next_index >= len(stages): return "QUEST_COMPLETE"
            
        quest["current_stage_index"] = next_index
        next_stage = stages[next_index]
        quest["objective"] = next_stage["objective"]
        quest["state"] = "active"
        
        self._setup_stage_mechanics(quest, next_stage)
        return completion_text
    
    def _setup_stage_mechanics(self, quest_data, stage_data):
        objective = stage_data.get("objective", {})
        if objective.get("is_procedural_item"):
            item_data = objective.get("procedural_item_data")
            # Some entries in world.regions (e.g. procedural-generation
            # theme definitions like "dynamic_themes") have no rooms and
            # must be excluded, or random.choice below can crash.
            populated_region_ids = [rid for rid, r in self.world.regions.items() if r.rooms]
            target_region_id = random.choice(populated_region_ids) if populated_region_ids else None
            region = self.world.get_region(target_region_id) if target_region_id else None
            if region:
                room_id = random.choice(list(region.rooms.keys()))
                item = ItemFactory.create_item_from_template(item_data["template_id"], self.world)
                if item:
                    item.name = item_data["name"]
                    item.description = f"The {item_data['name']}, requested for a quest."
                    self.world.add_item_to_room(target_region_id, room_id, item)
                    
        if objective.get("type") == "escort":
            spawn_conf = objective.get("spawn_config")
            if spawn_conf:
                npc = NPCFactory.create_npc_from_template(spawn_conf["template_id"], self.world, name=spawn_conf["name"])
                if npc:
                    npc.current_region_id = spawn_conf["region_id"]
                    npc.current_room_id = spawn_conf["room_id"]
                    npc.properties["is_escort_target"] = True
                    npc.properties["escort_quest_id"] = quest_data["instance_id"]
                    npc.behavior_type = "stationary" 
                    self.world.add_npc(npc)
                    objective["target_npc_instance_id"] = npc.obj_id

        # Stage-authored boss spawns occur when the stage begins.
        spawn_on_start = stage_data.get("spawn_on_start")
        if spawn_on_start:
             tid = spawn_on_start.get("template_id")
             rid = spawn_on_start.get("region_id")
             rmid = spawn_on_start.get("room_id")
             
             if tid and rid and rmid:
                  existing = [n for n in self.world.npcs.values() if n.template_id == tid and n.current_region_id == rid and n.is_alive]
                  if not existing:
                       boss = NPCFactory.create_npc_from_template(tid, self.world)
                       if boss:
                            boss.current_region_id = rid
                            boss.current_room_id = rmid
                            if "name_override" in spawn_on_start:
                                 boss.name = spawn_on_start["name_override"]
                            self.world.add_npc(boss)

    def handle_room_entry(self, player) -> List[str]:
        """Checks for scout objectives AND spawn triggers, returning update messages."""
        if player.runtime_state.quests is None:
            return []
        msgs = []
        for q_id, q_data in player.runtime_state.quests.active.items():
            if q_data["state"] != "active": continue
            
            stages = q_data.get("stages", [])
            idx = q_data.get("current_stage_index", 0)
            
            if stages and 0 <= idx < len(stages):
                current_stage = stages[idx]
                spawn_config = current_stage.get("spawn_on_entry")
                already_spawned = current_stage.get("_spawn_on_entry_triggered", False)
                
                if not spawn_config:
                    Logger.debug("spawn_on_entry", "We DO NOT have a spawn config.")
                if already_spawned:
                    Logger.debug("spawn_on_entry", "We have already spawned.")
                if spawn_config and not already_spawned:
                    Logger.debug("spawn_on_entry", "We have a spawn config and have not already spawned.")

                    req_region = spawn_config.get("region_id")
                    req_room = spawn_config.get("room_id")
                    
                    # DEBUG LOG
                    Logger.debug("spawn_on_entry", f"Checking spawn for {q_id}. Player at {player.current_region_id}:{player.current_room_id}. Req: {req_region}:{req_room}")
                    
                    if player.current_region_id == req_region and player.current_room_id == req_room:
                        Logger.debug("spawn_on_entry", "Player location matches spawn location.")
                        current_stage["_spawn_on_entry_triggered"] = True 
                        
                        tid = spawn_config.get("template_id")
                        if tid:
                            Logger.debug("spawn_on_entry", "1")
                            overrides = {}
                            if "name_override" in spawn_config:
                                overrides["name"] = spawn_config["name_override"]
                                Logger.debug("spawn_on_entry", "Name overwritten: " + overrides["name"])
                            if "behavior_type" in spawn_config:
                                overrides["behavior_type"] = spawn_config["behavior_type"]
                                Logger.debug("spawn_on_entry", "Behavior type overwritten: " + overrides["behavior_type"])
                            if "dialog" in spawn_config:
                                # Merge onto the base template's dialog rather than
                                # replacing it outright, so a spawn-specific greeting
                                # (e.g. a negotiation opener) doesn't silently drop
                                # the template's other lines (threat/flee/etc).
                                base_dialog = self.world.npc_templates.get(tid, {}).get("dialog", {})
                                overrides["dialog"] = {**base_dialog, **spawn_config["dialog"]}
                            boss = NPCFactory.create_npc_from_template(
                                tid, self.world, 
                                current_region_id=req_region,
                                current_room_id=req_room,
                                **overrides
                            )
                            if boss:
                                Logger.debug("spawn_on_entry", "We have a boss.")
                                self.world.add_npc(boss)
                                msgs.append(f"{FORMAT_HIGHLIGHT}A {boss.name} steps out from the shadows!{FORMAT_RESET}")
                                # Force immediate visibility check in renderer logic if needed
                            else:
                                Logger.debug("spawn_on_entry", "We DO NOT have a boss.")

            # --- Scout Logic ---
            objective = self.get_active_objective(q_data)
            if not objective: continue
            
            if objective.get("type") == "scout":
                if (player.current_region_id == objective.get("target_region") and 
                    player.current_room_id == objective.get("target_room_id")):
                    
                    q_data["state"] = "ready_to_complete"
                    quest_title = q_data.get("title", "Scouting Mission")
                    turn_in_name = self.resolve_turn_in_name(q_data)
                    msgs.append(f"{FORMAT_HIGHLIGHT}[Quest Update] {quest_title}{FORMAT_RESET}\n"
                                f"You have reached the target location. Report back to {turn_in_name}.")

        return msgs

    def handle_npc_killed(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        return handle_npc_killed(self, event_type, data)

    def handle_item_crafted(self, player, recipe, quality_tier: Optional[Dict[str, Any]]) -> Optional[str]:
        return handle_item_crafted(self, player, recipe, quality_tier)

    def handle_resource_gathered(self, player, resource_item_id: str) -> Optional[str]:
        return handle_resource_gathered(self, player, resource_item_id)

    def check_quest_completion(self, player=None):
        check_quest_completion(self, player)
