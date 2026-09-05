# engine/core/quest_generation/generator.py
import random
import uuid
from typing import TYPE_CHECKING, Dict, Any, Optional, List

from engine.config import QUEST_TYPES_NO_INSTANCE
from engine.utils.utils import simple_plural
from engine.npcs.npc import NPC
from engine.world.region_generator import RegionGenerator

# Import sub-modules
from .objectives import generate_kill_objective, generate_fetch_objective, generate_deliver_objective
from .text import format_quest_text, DEFAULT_TEXT_TEMPLATES
from .rewards import calculate_rewards
from engine.items.loot_generator import LootGenerator

if TYPE_CHECKING:
    from engine.world.world import World
    # Import the interface or class for QuestManager
    from engine.core.quests.manager import QuestManager

class QuestGenerator:
    def __init__(self, world: 'World', quest_manager: 'QuestManager'):
        self.world = world
        self.qm = quest_manager

    def generate_noninstance_quest(self, player_level: int, quest_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.world: return None
        if quest_type is None: quest_type = random.choice(QUEST_TYPES_NO_INSTANCE)
        
        giver_instance_id = self._select_giver_npc(quest_type)
        if not giver_instance_id: return None

        giver_npc = self.world.get_npc(giver_instance_id)
        if not giver_npc: return None

        objective_data = None
        # FIX: Call imported functions directly
        if quest_type == "kill": 
            objective_data = generate_kill_objective(self.world, player_level, giver_npc, self.qm.config)
        elif quest_type == "fetch": 
            objective_data = generate_fetch_objective(self.world, player_level, giver_npc, self.qm.config)
        elif quest_type == "deliver": 
            objective_data = generate_deliver_objective(self.world, player_level, giver_npc, self.qm.config)

        if not objective_data: return None
        
        objective_data["type"] = quest_type
        quest_id = f"quest_{quest_type}_{uuid.uuid4().hex[:6]}"
        
        # Calculate Rewards
        rewards = calculate_rewards(quest_type, objective_data, self.qm.config)

        # Generate Text
        temp_ctx = {"type": quest_type, "objective": objective_data}
        text_templates = self.qm.config.get("text_templates", DEFAULT_TEXT_TEMPLATES)
        title = format_quest_text("title", temp_ctx, giver_npc, text_templates)
        description = format_quest_text("description", temp_ctx, giver_npc, text_templates)

        stage_0 = {
            "stage_index": 0,
            "description": description,
            "objective": objective_data,
            "turn_in_id": giver_instance_id,
            "start_dialogue": "I need your help with this task.",
            "completion_dialogue": "You have my thanks."
        }

        quest_data = {
            "instance_id": quest_id,
            "type": "quest",
            "title": title,
            "giver_instance_id": giver_instance_id,
            "state": "available",
            "current_stage_index": 0,
            "stages": [stage_0],
            "rewards": rewards
        }

        return quest_data

    def generate_instance_quest(self, player_level: int) -> Optional[Dict[str, Any]]:
        valid_quests = [
            (qid, qd) for qid, qd in self.qm.quest_templates.items()
            if qd.get("type") == "instance" and qd.get("level", 1) <= player_level
        ]
        if not valid_quests: return None

        chosen_quest_id, chosen_template = random.choice(valid_quests)
        
        possible_creatures = chosen_template.get("objective", {}).get("possible_target_template_ids", [])
        if not possible_creatures: return None
        chosen_creature_id = random.choice(possible_creatures)
        
        objective_data = chosen_template.get("objective", {}).copy()
        objective_data["target_template_id"] = chosen_creature_id
        
        layout_config = chosen_template.get("layout_generation_config", {})
        instance_region_data = self._generate_random_house_layout(layout_config)

        possible_regions = chosen_template.get("possible_entry_regions", [self.world.content_set.start_region_id])
        valid_entry_points = []
        for region_id in possible_regions:
            region = self.world.get_region(region_id)
            if region:
                for room_id, room in region.rooms.items():
                    if self.world.is_location_outdoors(region_id, room_id):
                        valid_entry_points.append({"region_id": region_id, "room_id": room_id})
        
        if not valid_entry_points: return None
        chosen_entry = random.choice(valid_entry_points)
        instance_quest_config = self.qm.config.get("instance_quest", {})
        entry_point_data = {
            **chosen_entry,
            "exit_command": instance_quest_config.get("entry_exit_command", "enter"),
            "description_when_visible": instance_quest_config.get(
                "entry_description_when_visible", "Something unusual has appeared here."
            ),
        }

        quest_id = f"quest_inst_{uuid.uuid4().hex[:6]}"
        creature_template = self.world.npc_templates.get(chosen_creature_id, {})
        creature_name = simple_plural(creature_template.get("name", "Creature"))
        title = instance_quest_config.get("title_pattern", "Quest: {creature_name}").format(creature_name=creature_name)
        description = instance_quest_config.get("description_pattern", "Deal with the {creature_name}.").format(
            creature_name=creature_name
        )

        stage_0 = {
            "stage_index": 0,
            "description": description,
            "objective": objective_data,
            "turn_in_id": "quest_board"
        }

        quest_data = {
            "instance_id": quest_id,
            "type": "instance",
            "title": title,
            "state": "available",
            "giver_instance_id": "quest_board",
            "current_stage_index": 0,
            "stages": [stage_0],
            "rewards": chosen_template.get("rewards", {"xp": 100}),
            "meta_instance_data": { 
                "instance_region": instance_region_data,
                "entry_point": entry_point_data,
                "layout_config": layout_config,
                "giver_template_id": chosen_template.get("giver_npc_template_id")
            }
        }
        return quest_data

    def instantiate_quest(self, quest_template: Dict[str, Any], player_level: int) -> Dict[str, Any]:
        quest_instance = quest_template.copy()
        quest_instance["stages"] = []
        saga_context = {}
        generated_region_ids = []

        return self._instantiate_quest_logic(quest_instance, quest_template, player_level, saga_context, generated_region_ids)

    def _select_giver_npc(self, quest_type: str) -> Optional[str]:
        if not self.world: return None
        potential_givers = []
        for npc_instance in self.world.npcs.values():
            if (npc_instance and npc_instance.is_alive and npc_instance.faction != "hostile" and
                    npc_instance.properties.get("can_give_generic_quests")):
                template_id = getattr(npc_instance, 'template_id', None)
                if not template_id: continue
                npc_template_interests = self.qm.npc_interests.get(template_id, [])
                if quest_type in npc_template_interests:
                    potential_givers.append(npc_instance.obj_id)
        if not potential_givers: return None
        return random.choice(potential_givers)

    def _generate_random_house_layout(self, config: Dict[str, Any]) -> Dict[str, Any]:
        num_rooms = random.randint(config.get("min_rooms", 3), config.get("max_rooms", 7))
        possible_room_names = config.get("possible_room_names", ["Room"])
        rooms_data: Dict[str, Any] = {}
        
        rooms_data["room_0"] = {
            "name": "Entrance",
            "description": "The entrance.",
            "exits": {"out": "dynamic_exit"}
        }
        for i in range(1, num_rooms):
            rooms_data[f"room_{i}"] = {"name": random.choice(possible_room_names), "description": "A room.", "exits": {}}
            rooms_data[f"room_{i}"]["exits"]["south"] = f"room_{i-1}"
            rooms_data[f"room_{i-1}"]["exits"]["north"] = f"room_{i}"
            
        layout = {
            "region_name": config.get("region_name", "Place"),
            "region_description": "A place.",
            "rooms": rooms_data
        }
        return layout
        
    def _instantiate_quest_logic(self, quest_instance, quest_template, player_level, saga_context, generated_region_ids):
        # Procedural Regions
        if "procedural_regions" in quest_template:
            default_theme = self.qm.config.get("instance_quest", {}).get("default_procedural_theme", "")
            for region_conf in quest_template["procedural_regions"]:
                theme = region_conf.get("theme", default_theme)
                rooms_count = region_conf.get("rooms", 5)
                gen = RegionGenerator(self.world)
                result = gen.generate_region(theme, rooms_count)
                if result:
                    new_region, entry_room_id = result
                    new_region_id = new_region.obj_id
                    self.world.add_region(new_region_id, new_region)
                    generated_region_ids.append(new_region_id)
                    saga_context[region_conf.get("id_key", "procedural_region")] = new_region_id
                    
                    # Linking logic
                    link_info = region_conf.get("entry_point")
                    if link_info:
                        pr_id = link_info.get("region")
                        parent = self.world.get_region(pr_id)
                        if parent:
                            l_room_id = link_info.get("room") or random.choice(list(parent.rooms.keys()))
                            parent_room = parent.get_room(l_room_id)
                            if parent_room:
                                parent_room.exits["enter_quest"] = f"{new_region_id}:{entry_room_id}"
                            
                            entry_room_obj = new_region.get_room(entry_room_id)
                            if entry_room_obj:
                                entry_room_obj.exits["exit_quest"] = f"{pr_id}:{l_room_id}"

        if generated_region_ids: quest_instance["generated_region_ids"] = generated_region_ids
        
        # Rewards
        if "generate_rewards" in quest_template:
            gen = quest_template["generate_rewards"]
            rew = {}
            if "gold_range" in gen: rew["gold"] = random.randint(*gen["gold_range"])
            if "xp_range" in gen: rew["xp"] = random.randint(*gen["xp_range"])
            if "generate_item" in gen:
                ic = gen["generate_item"]
                item = LootGenerator.generate_loot(ic["base_template_id"], self.world, ic.get("level", player_level), ic.get("rarity", 0.5))
                if item: rew["generated_item_data"] = item.to_dict()
            quest_instance["rewards"] = rew

        # Stages
        previous_npc_id = None
        procedural_naming = self.qm.config.get("procedural_naming", {})
        self.adjectives = procedural_naming.get("adjectives", [])
        self.nouns = procedural_naming.get("nouns", [])

        for stage_template in quest_template.get("stages", []):
            new_stage = stage_template.copy()
            objective = new_stage.get("objective", {}).copy()
            
            if "target_region" in objective:
                val = objective["target_region"]
                if val.startswith("{") and val.endswith("}"):
                    key = val[1:-1]
                    if key in saga_context: objective["target_region"] = saga_context[key]

            obj_type = objective.get("type")

            if obj_type == "group_kill" and "targets_config" in objective:
                conf = objective.pop("targets_config")
                pool = conf.get("monster_pool", [])
                total_types = min(len(pool), conf.get("total_types", 1))
                count_range = conf.get("count_per_type_range", [1, 1])
                selected_types = random.sample(pool, total_types)
                targets_dict = {}
                for tid in selected_types:
                    count = random.randint(*count_range)
                    template = self.world.npc_templates.get(tid, {})
                    name = simple_plural(template.get("name", tid))
                    targets_dict[tid] = {"required": count, "current": 0, "name": name}
                objective["targets"] = targets_dict

            elif obj_type == "kill" and "target_config" in objective:
                conf = objective.pop("target_config")
                pool = conf.get("monster_pool", [])
                if pool:
                    tid = random.choice(pool)
                    count = conf.get("count", 1)
                    objective["target_template_id"] = tid
                    objective["required_quantity"] = count
                    objective["current_quantity"] = 0
                    template = self.world.npc_templates.get(tid, {})
                    objective["target_name"] = template.get("name", tid)

            elif obj_type == "fetch_procedural":
                base_tid = objective.get("base_template_id", procedural_naming.get("default_base_template_id", ""))
                if self.adjectives and self.nouns:
                    pattern = objective.get("name_pattern", procedural_naming.get("default_name_pattern", "{Noun}"))
                    adj = random.choice(self.adjectives)
                    noun = random.choice(self.nouns)
                    item_name = pattern.format(Adjective=adj, Noun=noun)
                else:
                    base_template = self.world.item_templates.get(base_tid, {})
                    item_name = base_template.get("name", base_tid or "Unknown Item")
                saga_context["item_name"] = item_name
                objective["type"] = "fetch"
                objective["item_name"] = item_name
                objective["is_procedural_item"] = True
                objective["procedural_item_data"] = {
                    "template_id": base_tid, "name": item_name
                }
            
            elif obj_type == "scout":
                target_region_id = objective.get("target_region")
                keywords = objective.get("target_room_keywords", [])
                target_room_id = None
                
                region = self.world.get_region(target_region_id)
                if region:
                    candidates = []
                    for rid, room in region.rooms.items():
                        if not keywords or any(k in rid or k in room.name.lower() for k in keywords):
                            candidates.append(rid)
                    if not candidates and not keywords:
                        candidates = list(region.rooms.keys())
                    if candidates: target_room_id = random.choice(candidates)
                
                if target_room_id and region:
                    objective["target_room_id"] = target_room_id
                    target_room = region.get_room(target_room_id)
                    room_name = target_room.name if target_room else "Unknown Room"
                    objective["location_hint"] = f"{room_name} in {region.name}"
                else:
                    objective["target_room_id"] = "unknown"
                    objective["location_hint"] = "Unknown Location"

            new_stage["objective"] = objective

            turn_in_conf = new_stage.get("turn_in_config")
            
            if turn_in_conf == "SAME_AS_PREVIOUS" and previous_npc_id:
                new_stage["turn_in_id"] = previous_npc_id
            elif isinstance(turn_in_conf, dict):
                candidates = []
                for npc in self.world.npcs.values():
                    if not npc.is_alive: continue
                    match = True
                    if "npc_pool_faction" in turn_in_conf and npc.faction != turn_in_conf["npc_pool_faction"]: match = False
                    if "npc_pool_region" in turn_in_conf and npc.current_region_id != turn_in_conf["npc_pool_region"]: match = False
                    if match: candidates.append(npc.obj_id)
                
                if candidates:
                    chosen_id = random.choice(candidates)
                    new_stage["turn_in_id"] = chosen_id
                    previous_npc_id = chosen_id
                else:
                    new_stage["turn_in_id"] = "quest_board"
                    previous_npc_id = "quest_board"
            
            if "turn_in_id" in new_stage:
                previous_npc_id = new_stage["turn_in_id"]

            if "description" in new_stage:
                try: new_stage["description"] = new_stage["description"].format(**saga_context)
                except KeyError: pass

            quest_instance["stages"].append(new_stage)

        return quest_instance
