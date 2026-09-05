# engine/commands/interaction/npcs.py
from typing import List, Optional, Any
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE,
    FOLLOW_COMMAND_STOP_ALIASES
)
from engine.config.config_display import FORMAT_CATEGORY
from engine.core.skill_system import SkillSystem
from engine.utils.utils import format_name_for_display

def _resolve_target_npc(world, args, player):
    """Helper to resolve NPC target based on arguments or context."""
    npcs_in_room = world.get_npcs_for_player(player)
    
    # 1. Try fuzzy match from args
    if args:
        for i in range(len(args), 0, -1):
            potential_name = " ".join(args[:i]).lower()
            for npc in npcs_in_room:
                if npc.name.lower() == potential_name or npc.obj_id == potential_name:
                    return npc, i
            for npc in npcs_in_room:
                if potential_name in npc.name.lower():
                    return npc, i
    
    # 2. Fallback to context
    if player.trading_with:
        return world.get_npc(player.trading_with), 0
    elif player.last_talked_to:
        candidate = world.get_npc(player.last_talked_to)
        if candidate and candidate.current_region_id == player.current_region_id and candidate.current_room_id == player.current_room_id:
            return candidate, 0
            
    # 3. Fallback to any valid NPC
    valid_npcs = [n for n in npcs_in_room if n.faction != "hostile" and n.faction != "player_minion"]
    if valid_npcs:
        return valid_npcs[0], 0
        
    return None, 0

# "ask" is intentionally not an alias here -- the dedicated "ask <npc>
# <topic>" command already owns that word (and loads after this module),
# so it silently wins over this one.
@command("talk", ["speak", "chat"], "interaction", "Talk to an NPC.\nUsage: talk <npc_name> [topic | complete quest]")
def talk_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    
    if args and args[0].lower() == "to": args = args[1:]
    
    target_npc, match_len = _resolve_target_npc(world, args, player)

    if not target_npc: return f"{FORMAT_ERROR}There is no one here to talk to.{FORMAT_RESET}"
    
    if target_npc.faction == "hostile":
        formatted_name = format_name_for_display(player, target_npc, start_of_sentence=True)
        return f"{formatted_name} {FORMAT_ERROR}refuses to listen and prepares to attack!{FORMAT_RESET}"

    player.last_talked_to = target_npc.obj_id

    remaining_args = args[match_len:]
    topic = None
    is_quest_turn_in = False
    
    if remaining_args:
        if remaining_args[0].lower() == "about": remaining_args.pop(0)
        topic_str = " ".join(remaining_args)
        # Quest turn-in phrases only intercept dialogue when quests are
        # actually enabled -- otherwise a dialogue-only content set is free
        # to author its own "complete"/"negotiate" topics without them
        # being silently stolen.
        quest_phrases = (
            world.ruleset_section("quest_generation").get(
                "turn_in_phrases", ["complete", "turn in", "turnin"]
            )
            if world.has_capability("quests")
            else []
        )
        if topic_str.lower() in quest_phrases:
            is_quest_turn_in = True
        else:
            topic = topic_str

    if is_quest_turn_in:
        return _handle_quest_dialogue(player, target_npc, world)
    
    if topic:
         manager = world.game.knowledge_manager
         player.conversation.mark_discussed(target_npc.obj_id, topic)
         topic_id = manager.resolve_topic_id(topic)
         if not topic_id: topic_id = topic.lower().replace(" ", "_")
         
         raw_response = manager.get_response(target_npc, topic_id, player)
         
         if raw_response is None:
             topic_display = manager.topics.get(topic_id, {}).get("display_name", topic)
             return f"{target_npc.name} has nothing to say about {topic_display}."

         formatted_response = manager.parse_and_highlight(raw_response, player, source_npc=target_npc, exclude_topic_id=topic_id)
         return f"{FORMAT_TITLE}{target_npc.name}{FORMAT_RESET}: {formatted_response}"

    # Default Greeting / Status Check
    ready_quests_for_npc = []
    active_quests_for_npc = []
    
    if player.runtime_state.quests is not None and player.runtime_state.quests.active:
        for q_id, q_data in player.runtime_state.quests.active.items():
            stages = q_data.get("stages", [])
            idx = q_data.get("current_stage_index", 0)
            
            turn_in_target = q_data.get("giver_instance_id")
            if stages and idx < len(stages):
                stage_target = stages[idx].get("turn_in_id")
                if stage_target: turn_in_target = stage_target

            if turn_in_target == target_npc.obj_id or turn_in_target == target_npc.template_id:
                if q_data.get("state") == "ready_to_complete":
                    ready_quests_for_npc.append(q_data)
                elif q_data.get("state") == "active":
                    active_quests_for_npc.append(q_data)
    
    hints = []
    raw_response = target_npc.talk()
    
    # Priority Overrides for Greeting
    if ready_quests_for_npc:
        quest_title = ready_quests_for_npc[0].get("title", "the mission")
        raw_response = f"I see you have returned. Do you have news regarding {quest_title}?"
        hints.append(f"Type '{FORMAT_HIGHLIGHT}talk {target_npc.name} complete{FORMAT_RESET}' to report success.")
    elif active_quests_for_npc:
         # Optionally mention waiting
         pass
    elif target_npc.properties.get("can_give_generic_quests", False):
         hints.append(f"Try '{FORMAT_HIGHLIGHT}ask {target_npc.name} job{FORMAT_RESET}' or '{FORMAT_HIGHLIGHT}rumors{FORMAT_RESET}'.")
    
    formatted_response = world.game.knowledge_manager.parse_and_highlight(raw_response, player, source_npc=target_npc)
    
    npc_title = f"{FORMAT_TITLE}CONVERSATION WITH {target_npc.name.upper()}{FORMAT_RESET}\n\n"
    output = f"{npc_title}\"{formatted_response}\""
    if hints: output += "\n\n" + "\n".join(hints)
        
    return output

@command("ask", ["topic", "query"], "interaction", "Ask an NPC about a topic.\nUsage: ask [npc_name] [about] <topic>")
def ask_handler(args, context):
    world = context["world"]
    player = context.get('player')
    manager = world.game.knowledge_manager

    if not args: return f"{FORMAT_ERROR}Ask who/what? Usage: ask [npc_name] <topic>{FORMAT_RESET}"

    target_npc, match_len = _resolve_target_npc(world, args, player)
    
    if not target_npc: return f"{FORMAT_ERROR}There is no one here to ask.{FORMAT_RESET}"
    if target_npc.faction == "hostile":
        return f"{target_npc.name} {FORMAT_ERROR}refuses to listen.{FORMAT_RESET}"

    player.last_talked_to = target_npc.obj_id

    topic_words = args[match_len:]
    if topic_words and topic_words[0].lower() == "about": topic_words.pop(0)

    if not topic_words: return f"{FORMAT_ERROR}Ask {target_npc.name} about what?{FORMAT_RESET}"
    
    raw_input = " ".join(topic_words)
    topic_id = manager.resolve_topic_id(raw_input)
    if not topic_id: topic_id = raw_input.lower().replace(" ", "_")

    player.conversation.mark_discussed(target_npc.obj_id, topic_id)
    raw_response = manager.get_response(target_npc, topic_id, player)
    
    if raw_response is None:
        topic_display = manager.topics.get(topic_id, {}).get("display_name", raw_input)
        return f"{target_npc.name} has nothing to say about {topic_display}."

    formatted_response = manager.parse_and_highlight(raw_response, player, source_npc=target_npc, exclude_topic_id=topic_id)
    return f"{FORMAT_TITLE}{target_npc.name}{FORMAT_RESET}: {formatted_response}"

def handle_accept_offer(args, context):
    """
    Called by 'accept' command when not at a quest board.
    Attempts to accept an offer from the focused NPC.
    """
    world = context["world"]
    player = context.get('player')
    manager = world.game.knowledge_manager
    
    target_npc, _ = _resolve_target_npc(world, [], player)
    
    if not target_npc:
        return "No one here has offered you anything."

    topic_id = manager.resolve_topic_id("accept")
    if not topic_id: topic_id = "accept_mission"
    
    raw_response = manager.get_response(target_npc, topic_id, player)
    
    if raw_response is None:
        return "No one here has offered you anything."
        
    formatted_response = manager.parse_and_highlight(raw_response, player, source_npc=target_npc)
    return f"{FORMAT_TITLE}{target_npc.name}{FORMAT_RESET}: {formatted_response}"

@command("turnin", ["donate", "deposit"], "interaction", "Turn in collection items to a collector.\nUsage: turnin")
def turnin_handler(args, context):
    world = context["world"]; player = context.get('player'); game = context["game"]; manager = game.collection_manager 
    if not player: return "Error."
    target_npc = None
    if player.trading_with: target_npc = world.get_npc(player.trading_with)
    elif player.last_talked_to:
        c = world.get_npc(player.last_talked_to)
        if c and c.current_room_id == player.current_room_id: target_npc = c
    if not target_npc:
        for npc in world.get_npcs_for_player(player):
            if npc.properties.get("is_collector"): target_npc = npc; break
    if not target_npc: return f"{FORMAT_ERROR}There is no one here to accept collections.{FORMAT_RESET}"
    return manager.turn_in_items(player, target_npc)

@command("follow", [], "interaction", "Follow an NPC.\nUsage: follow <npc_name> | follow stop")
def follow_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot move.{FORMAT_RESET}"
    if not args:
        target_npc = world.get_npc(player.follow_target) if player.follow_target else None
        target_name = target_npc.name if target_npc else "someone"
        return f"You are currently following {target_name}. Type 'follow stop'." if player.follow_target else "Follow whom?"
    cmd_arg = " ".join(args).lower()
    if cmd_arg in FOLLOW_COMMAND_STOP_ALIASES:
        if player.follow_target: player.follow_target = None; return f"{FORMAT_HIGHLIGHT}You stop following.{FORMAT_RESET}"
        else: return "You aren't following anyone."
    found_npc = world.find_npc_in_room_for_player(cmd_arg, player)
    if found_npc:
        if player.follow_target == found_npc.obj_id: return f"You are already following {found_npc.name}."
        player.follow_target = found_npc.obj_id
        return f"{FORMAT_HIGHLIGHT}You start following {found_npc.name}.{FORMAT_RESET}"
    else: return f"{FORMAT_ERROR}No '{cmd_arg}' here to follow.{FORMAT_RESET}"

@command("guide", [], "interaction", "Ask a quest giver to guide you to your destination.\nUsage: guide <npc_name>", content_capability="quests")
def guide_handler(args, context):
    world = context["world"]; player = context.get('player'); game = context["game"]
    if not player or not game: return f"{FORMAT_ERROR}System error: context missing.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Who do you want to guide you?{FORMAT_RESET}"

    npc_name = " ".join(args); guide_npc = world.find_npc_in_room_for_player(npc_name, player)
    if not guide_npc: return f"{FORMAT_ERROR}You don't see '{npc_name}' here.{FORMAT_RESET}"
    
    if guide_npc.faction == "hostile": return f"{FORMAT_ERROR}{guide_npc.name} growls at you. They won't guide you anywhere.{FORMAT_RESET}"

    quest_to_guide = None
    if player.runtime_state.quests is not None:
        for quest in player.runtime_state.quests.active.values():
            if quest.get("giver_instance_id") == guide_npc.obj_id and quest.get("type") == "instance": quest_to_guide = quest; break
    
    if not quest_to_guide: return f"{guide_npc.name} has not offered to guide you anywhere."
    entry_point = quest_to_guide.get("entry_point")
    if not entry_point: return f"{FORMAT_ERROR}Quest '{quest_to_guide.get('title')}' has no destination.{FORMAT_RESET}"

    destination_region = entry_point.get("region_id"); destination_room = entry_point.get("room_id")
    path = world.find_path(player.current_region_id, player.current_room_id, destination_region, destination_room)

    if path is None: return f"{guide_npc.name} seems confused and can't find a path from here."
    if not path: return f"You are already at the destination!"

    game.start_auto_travel(path, guide_npc)
    return f"{FORMAT_HIGHLIGHT}\"{guide_npc.dialog.get('accept_guide', 'Follow me!')}\"{FORMAT_RESET}"

def _handle_quest_dialogue(player, target_npc, world) -> str:
    ready_quests_for_npc = []
    quest_manager = world.quest_manager

    if player.runtime_state.quests is not None and player.runtime_state.quests.active:
        for q_id, q_data in player.runtime_state.quests.active.items():
            stages = q_data.get("stages", [])
            idx = q_data.get("current_stage_index", 0)
            turn_in_target = q_data.get("giver_instance_id") 
            if stages and idx < len(stages):
                 stage_target = stages[idx].get("turn_in_id")
                 if stage_target: turn_in_target = stage_target
                 objective = stages[idx].get("objective", {})
                 if objective.get("type") == "negotiate":
                      target_tid = objective.get("target_npc_id")
                      if target_tid == target_npc.template_id or target_tid == target_npc.obj_id:
                           turn_in_target = target_npc.obj_id
            state = q_data.get("state")
            objective = quest_manager.get_active_objective(q_data) or {} 
            objective_type = objective.get("type")
            is_target_npc = (turn_in_target == target_npc.obj_id) or (turn_in_target == target_npc.template_id)
            is_ready = False
            if state == "ready_to_complete" and is_target_npc:
                is_ready = True
            elif state == "active" and is_target_npc:
                if objective_type in ["fetch", "deliver", "talk", "negotiate", "dialogue_choice"]:
                    is_ready = True
            if is_ready:
                ready_quests_for_npc.append((q_id, q_data))

    if not ready_quests_for_npc: return f"{target_npc.name} doesn't seem to be expecting anything from you right now."
    quest_turn_in_id, quest_data = ready_quests_for_npc[0]
    objective = quest_manager.get_active_objective(quest_data)
    if not objective:
        return f"{FORMAT_ERROR}Error: Quest objective data missing for '{quest_data.get('title')}'.{FORMAT_RESET}"

    can_complete = True
    completion_error_msg = ""
    
    if objective.get("type") == "negotiate":
        skill = objective.get("skill", "diplomacy")
        difficulty = objective.get("difficulty", 10)
        success, msg = SkillSystem.attempt_check(player, skill, difficulty)
        choices = objective.get("choices", {})
        choice_id = "success" if success else "fail"
        if choice_id in choices:
            qm = world.quest_manager
            dialogue = qm.advance_quest_stage(player, quest_turn_in_id, choice_id=choice_id)
            if dialogue == "QUEST_COMPLETE":
                 rewards_msg = qm.complete_quest(player, quest_turn_in_id)
                 return f"{FORMAT_SUCCESS}[Quest Complete] {quest_data.get('title')}{FORMAT_RESET}\n{FORMAT_HIGHLIGHT}\"Negotiation concluded.\"{FORMAT_RESET}"
            outcome_desc = choices[choice_id].get("description", "Result")
            status_color = FORMAT_SUCCESS if success else FORMAT_ERROR
            return f"{status_color}[Negotiation {choice_id.upper()}]{FORMAT_RESET} {msg}\n\n{FORMAT_HIGHLIGHT}\"{dialogue}\"{FORMAT_RESET}\n({outcome_desc})"
        else: return f"{FORMAT_ERROR}Negotiation config error.{FORMAT_RESET}"

    req_item_id = objective.get("item_id")
    item_to_remove = None
    req_qty = objective.get("required_quantity", 1)

    if req_item_id:
        if objective.get("type") == "deliver" and objective.get("item_instance_id"):
             item_to_remove = player.inventory.find_item_by_id(objective["item_instance_id"])
             if not item_to_remove:
                 can_complete = False
                 completion_error_msg = f"You don't have the {objective.get('item_to_deliver_name', 'package')}."
        else:
             current_count = player.inventory.count_item(req_item_id)
             if current_count < req_qty:
                 can_complete = False
                 remaining = req_qty - current_count
                 completion_error_msg = f"You still need {remaining} more {objective.get('item_name', 'items')}."

    if can_complete and req_item_id:
        if objective.get("type") == "deliver" and item_to_remove:
             player.inventory.remove_item_instance(item_to_remove)
        else:
             player.inventory.remove_item(req_item_id, req_qty)

    if can_complete:
        qm = world.quest_manager
        dialogue = qm.advance_quest_stage(player, quest_turn_in_id)
        
        if dialogue == "QUEST_COMPLETE":
            # DETERMINE RESOLUTION
            objective = qm.get_active_objective(quest_data) or {}
            obj_type = objective.get("type", "unknown")
            resolution = "SUCCESS"
            
            if obj_type == "kill" or obj_type == "clear_region":
                resolution = "VIOLENT_SUCCESS"
            elif obj_type in ["negotiate", "talk", "deliver", "fetch"]:
                resolution = "PEACEFUL_SUCCESS"
            
            rewards_msg = qm.complete_quest(player, quest_turn_in_id, resolution=resolution)
            
            title = quest_data.get('title', 'Quest')
            completion_msg = f"{FORMAT_SUCCESS}[Quest Complete] {title}{FORMAT_RESET}\n"
            if not dialogue or dialogue == "QUEST_COMPLETE":
                 dialogue = target_npc.dialog.get("quest_complete", f"\"Thank you!\" says {target_npc.name}.")
            completion_msg += f"{FORMAT_HIGHLIGHT}\"{dialogue}\"{FORMAT_RESET}"
            if rewards_msg: completion_msg += f"\n{rewards_msg}"
            return completion_msg
        else:
            new_idx = quest_data.get("current_stage_index", 0)
            new_stage_desc = quest_data["stages"][new_idx]["description"]
            return f"{FORMAT_SUCCESS}[Objective Complete]{FORMAT_RESET}\n{FORMAT_HIGHLIGHT}\"{dialogue}\"{FORMAT_RESET}\n\n{FORMAT_CATEGORY}New Objective:{FORMAT_RESET} {new_stage_desc}"
            
    else: 
        return f"{FORMAT_ERROR}You haven't fully met the requirements. {completion_error_msg}{FORMAT_RESET}"
    
@command("negotiate", ["parley"], "interaction", "Attempt to negotiate with an NPC.\nUsage: negotiate <npc>", content_capability="quests")
def negotiate_handler(args, context):
    """Shortcut command that proxies to 'talk <npc> negotiate'."""
    # This tricks the talk_handler into thinking we typed 'talk <npc> negotiate'
    # which triggers the quest logic update we made above.
    return talk_handler(args + ["negotiate"], context)
