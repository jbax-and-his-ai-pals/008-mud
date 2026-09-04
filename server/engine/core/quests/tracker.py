# engine/core/quests/tracker.py
from typing import Dict, Any, Optional
from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET
from engine.npcs.npc_factory import NPCFactory

def handle_npc_killed(manager, event_type: str, data: Dict[str, Any]) -> Optional[str]:
    player = data.get("player")
    killed_npc = data.get("npc")
    if not manager.world or not player or not killed_npc or player.runtime_state.quests is None:
        return None
    
    killed_template_id = getattr(killed_npc, 'template_id', None)
    if not killed_template_id: return None
    
    messages = []
    for quest_id, quest_data in list(player.runtime_state.quests.active.items()):
        if quest_data.get("state") != "active": continue

        objective = manager.get_active_objective(quest_data)
        if not objective: continue

        obj_type = objective.get("type")
        
        if obj_type == "kill":
            if objective.get("target_template_id") == killed_template_id:
                _update_standard_kill(manager, quest_data, objective, messages)

        elif obj_type == "group_kill" and "targets" in objective:
            targets = objective["targets"]
            if killed_template_id in targets:
                target_data = targets[killed_template_id]
                if target_data["current"] < target_data["required"]:
                    target_data["current"] += 1
                    all_complete = all(t["current"] >= t["required"] for t in targets.values())
                    target_name = target_data.get("name", "Enemy")
                    
                    if all_complete:
                            quest_data["state"] = "ready_to_complete"
                            # Manager must have this method exposed
                            turn_in_name = manager.resolve_turn_in_name(quest_data)
                            messages.append(f"{FORMAT_HIGHLIGHT}[Quest Update]{FORMAT_RESET} {quest_data.get('title')}: All targets eliminated! Report to {turn_in_name}.")
                    else:
                            messages.append(f"{FORMAT_HIGHLIGHT}[Quest Update]{FORMAT_RESET} {quest_data.get('title')}: {target_name} ({target_data['current']}/{target_data['required']})")

    return "\n".join(messages) if messages else None

def _update_standard_kill(manager, quest_data, objective, messages):
    objective["current_quantity"] = objective.get("current_quantity", 0) + 1
    required = objective.get("required_quantity", 1)
    title = quest_data.get("title", "Task")
    
    stages = quest_data.get("stages", [])
    idx = quest_data.get("current_stage_index", 0)
    if stages and idx < len(stages):
        desc = stages[idx].get("description", "Task")
        title = f"{title} ({desc})"
    
    if objective["current_quantity"] >= required:
        quest_data["state"] = "ready_to_complete"
        # Manager must have this method
        turn_in_name = manager.resolve_turn_in_name(quest_data)
        messages.append(f"{FORMAT_HIGHLIGHT}[Quest Update]{FORMAT_RESET} {title}: Objective complete! Report back to {turn_in_name}.")
    else:
        messages.append(f"{FORMAT_HIGHLIGHT}[Quest Update]{FORMAT_RESET} {title}: ({objective['current_quantity']}/{required} killed).")

def check_quest_completion(manager, player=None):
    """
    Checks for quests that auto-complete based on world state (e.g., Clear Region).
    """
    if not manager.world:
        return

    players = []
    if player is not None:
        players = [player]
    elif getattr(manager.world, "players", None):
        players = list(manager.world.players.values())
    else:
        fallback_player = manager.world.resolve_reference_player()
        if fallback_player is not None:
            players = [fallback_player]

    for tracked_player in players:
        if not tracked_player or tracked_player.runtime_state.quests is None or not tracked_player.runtime_state.quests.active:
            continue

        for quest_id, quest_data in list(tracked_player.runtime_state.quests.active.items()):
            if quest_data.get("state") != "active":
                continue
            if not quest_data.get("completion_check_enabled", False):
                continue

            objective = manager.get_active_objective(quest_data)
            if not objective:
                objective = quest_data.get("objective", {})

            if objective.get("type") != "clear_region":
                continue

            instance_region_id = quest_data.get("instance_region_id")
            target_template_id = objective.get("target_template_id")
            if not instance_region_id or not target_template_id:
                continue

            hostiles_remaining = sum(
                1 for npc in manager.world.npcs.values()
                if npc.is_alive and npc.current_region_id == instance_region_id and npc.template_id == target_template_id
            )

            if hostiles_remaining != 0:
                continue

            if manager.world.game and manager.world.game.renderer:
                completion_npc_tid = objective.get("completion_npc_template_id")
                completion_npc_template = manager.world.npc_templates.get(str(completion_npc_tid))
                completion_npc_name = completion_npc_template.get("name", "the quest giver") if completion_npc_template else "the quest giver"

                meta = quest_data.get("meta_instance_data", {})
                instance_region = meta.get("instance_region", {})
                instance_name = instance_region.get("region_name", "area")

                message = f"{FORMAT_HIGHLIGHT}[Quest Update] You have cleared the {instance_name}! Report back to {completion_npc_name} outside.{FORMAT_RESET}"
                manager.world.game.renderer.add_message(message)

            quest_data["state"] = "ready_to_complete"

            original_giver_id = quest_data.get("giver_instance_id")
            if original_giver_id and isinstance(original_giver_id, str) and original_giver_id.startswith("giver_"):
                if original_giver_id in manager.world.npcs:
                    del manager.world.npcs[original_giver_id]

                completion_npc_tid = objective.get("completion_npc_template_id")
                if completion_npc_tid:
                    meta = quest_data.get("meta_instance_data", {})
                    entry_point = meta.get("entry_point", {})
                    spawn_region = entry_point.get("region_id")
                    spawn_room = entry_point.get("room_id")

                    if spawn_region and spawn_room:
                        completion_npc = NPCFactory.create_npc_from_template(
                            completion_npc_tid,
                            manager.world,
                            original_giver_id,
                            current_region_id=spawn_region,
                            current_room_id=spawn_room,
                        )
                        if completion_npc:
                            manager.world.add_npc(completion_npc)
                            player_in_spawn_room = (
                                getattr(tracked_player, "current_region_id", None) == spawn_region
                                and getattr(tracked_player, "current_room_id", None) == spawn_room
                            )
                            if manager.world.game and player_in_spawn_room:
                                manager.world.game.renderer.add_message(
                                    f"{FORMAT_HIGHLIGHT}The homeowner returns, looking much more cheerful now.{FORMAT_RESET}"
                                )

