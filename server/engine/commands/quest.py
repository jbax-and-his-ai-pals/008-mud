# engine/commands/quest.py
import uuid
from engine.commands.command_system import command, registered_commands
from engine.config import FORMAT_SUCCESS, FORMAT_ERROR, FORMAT_RESET, FORMAT_HIGHLIGHT, FORMAT_CATEGORY, FORMAT_TITLE, QUEST_BOARD_ALIASES
from engine.items.item_factory import ItemFactory
from engine.player import Player
from engine.world import world

# Need to import handle_accept_offer
from engine.commands.interaction.npcs import handle_accept_offer

def _is_player_at_quest_board(player: Player, quest_manager) -> bool:
    """Checks if the player's current location is one of the valid quest board locations."""
    board_locations = quest_manager.config.get("quest_board_locations", [])
    player_location_str = f"{player.current_region_id}:{player.current_room_id}"
    return player_location_str in board_locations

@command(name="look board", aliases=QUEST_BOARD_ALIASES, category="interaction", help_text="Look at the quest board for available tasks.", content_capability="quests")
def look_board_handler(args, context):
    world = context["world"]
    player = context.get('player')
    quest_manager = world.quest_manager

    if not _is_player_at_quest_board(player, quest_manager):
        return f"{FORMAT_ERROR}You don't see a {world.quest_board_name().lower()} here.{FORMAT_RESET}"

    available_quests = world.quest_board

    board_name = world.quest_board_name()
    if not available_quests:
        return f"The {board_name.lower()} is currently empty."

    response = f"{FORMAT_TITLE}{board_name}{FORMAT_RESET}\n" + "-"*20 + "\nAvailable Tasks:\n\n"
    for i, quest_data in enumerate(available_quests):
        giver_instance_id = quest_data.get("giver_instance_id")
        rewards = quest_data.get("rewards", {})

        giver_name = f"{board_name} Notice"
        if giver_instance_id != "quest_board":
            giver_npc = world.get_npc(giver_instance_id) 
            giver_name = giver_npc.name if giver_npc else "Unknown"

        # Use helper for safety
        objective = quest_manager.get_active_objective(quest_data) or {}
        quest_type = objective.get("type", "unknown")
        
        quantity_summary = ""
        if quest_type in ["kill", "fetch"]:
            quantity = objective.get("required_quantity")
            if quantity:
                quantity_summary = f" ({quantity})"
        
        response += (f"{FORMAT_CATEGORY}[{i + 1}]{FORMAT_RESET} {quest_data.get('title', 'Unnamed Quest')}{FORMAT_HIGHLIGHT}{quantity_summary}{FORMAT_RESET}\n"
                    f"   Giver: {giver_name}\n"
                    f"   Reward: {rewards.get('xp', 0)} XP, {rewards.get('gold', 0)} {world.currency_name().capitalize()}\n\n")
        
    response += f"Type '{FORMAT_HIGHLIGHT}accept quest <#>{FORMAT_RESET}' to take a task."
    return response

@command(name="accept quest", aliases=["accept"], category="interaction", help_text="Accept a quest from the board or an offer from an NPC.\nUsage: accept <# | topic>", content_capability="quests")
def accept_quest_handler(args, context):
    """
    Handles accepting quests.
    1. If args are numeric (e.g. "accept 1"), it interacts with the Quest Board.
    2. If args are text (e.g. "accept mission"), it delegates to NPC dialogue.
    """
    world = context["world"]
    player = context.get('player')
    quest_manager = world.quest_manager

    # --- 1. DETERMINE TARGET (Board vs NPC) ---
    is_numeric = False
    quest_index = -1
    
    if args:
        # Check for "quest 1" or just "1"
        target_arg = args[0]
        if target_arg.lower() == "quest" and len(args) > 1:
            target_arg = args[1]
        
        if target_arg.isdigit():
            is_numeric = True
            quest_index = int(target_arg) - 1

    # --- 2. NPC CONVERSATION FALLBACK ---
    # If not a number, or if we aren't at a board, try to accept offer from NPC
    at_board = _is_player_at_quest_board(player, quest_manager)
    
    if not is_numeric or not at_board:
        # Call the dedicated handler for NPC offers
        return handle_accept_offer(args, context)

    # --- 3. QUEST BOARD LOGIC ---
    if quest_index < 0 or quest_index >= len(world.quest_board):
        return f"{FORMAT_ERROR}Invalid quest number.{FORMAT_RESET}"

    quest_to_accept = world.quest_board.pop(quest_index)
    quest_to_accept["state"] = "active"
    quest_instance_id = quest_to_accept.get("instance_id")

    # --- INSTANCE QUEST HANDLING ---
    meta_data = quest_to_accept.get("meta_instance_data")
    acceptance_message = ""
    
    if meta_data:
        # Flatten for the manager call
        quest_to_accept.update(meta_data)
        quest_to_accept["completion_check_enabled"] = False
        
        success, message, giver_npc_id = world.instantiate_quest_region(quest_to_accept, requesting_player=player)
        
        if not success:
            world.quest_board.insert(quest_index, quest_to_accept)
            return f"{FORMAT_ERROR}Could not start quest: {message}{FORMAT_RESET}"
            
        # Update Giver info if dynamically spawned
        if giver_npc_id:
            # Update stage 0 turn-in to the specific giver instance
            quest_to_accept["stages"][0]["turn_in_id"] = giver_npc_id
            quest_to_accept["giver_instance_id"] = giver_npc_id
            
            giver_npc = world.get_npc(giver_npc_id)
            if giver_npc:
                 entry_point = meta_data.get("entry_point", {})
                 entry_region = world.get_region(entry_point.get("region_id"))
                 entry_room = entry_region.get_room(entry_point.get("room_id")) if entry_region else None
                 location_desc = entry_room.name if entry_room else "a nearby house"
                 
                 extended = giver_npc.dialog.get("greeting_extended", "").format(entry_location_desc=location_desc)
                 message += f" \"{extended}\""
        
        acceptance_message = f"{FORMAT_SUCCESS}[Quest Accepted] {quest_to_accept.get('title')}{FORMAT_RESET}\n{FORMAT_HIGHLIGHT}{message}{FORMAT_RESET}"

    # --- STANDARD QUEST HANDLING ---
    else:
        # Check if first stage is 'deliver' to grant items
        objective = quest_manager.get_active_objective(quest_to_accept)
        if objective and objective.get("type") == "deliver":
             # Create Package
             pkg = ItemFactory.create_item_from_template(
                 objective["item_template_id"], world,
                 obj_id=objective["item_instance_id"],
                 name=objective["item_to_deliver_name"],
                 description=objective["item_to_deliver_description"]
             )
             can, msg = player.inventory.can_add_item(pkg)
             if not can:
                 world.quest_board.insert(quest_index, quest_to_accept)
                 return f"{FORMAT_ERROR}Inventory full: {msg}{FORMAT_RESET}"
             player.inventory.add_item(pkg)
             acceptance_message = f"{FORMAT_SUCCESS}[Quest Accepted] {quest_to_accept.get('title')}{FORMAT_RESET}\n(You received the package)"
        else:
             acceptance_message = f"{FORMAT_SUCCESS}[Quest Accepted] {quest_to_accept.get('title')}{FORMAT_RESET}"

    player.runtime_state.quests.active[quest_instance_id] = quest_to_accept
    quest_manager.replenish_board(None, player)
    return acceptance_message + "\n(Check your 'journal' for details)"

@command(name="journal", aliases=["quests", "log", "j"], category="information",
         help_text="View your active or completed quests.\nUsage: journal [completed]", content_capability="quests")
def journal_handler(args, context):
    player = context.get("player")
    if not player:
        return "Player not found."
    active_quests = player.runtime_state.quests.active
    completed_quests = player.runtime_state.quests.completed

    if args and args[0].lower() == "completed":
        all_completed_quests = {**player.runtime_state.quests.completed, **player.runtime_state.quests.archived}
        if not all_completed_quests:
            return "You have not completed any quests yet."
        
        response = f"{FORMAT_TITLE}Completed Quests ({len(all_completed_quests)}){FORMAT_RESET}\n{'-'*20}\n\n"
        sorted_completed = sorted(all_completed_quests.values(), key=lambda q: q.get("title", ""))
        
        for quest_data in sorted_completed:
            response += f"- {quest_data.get('title', 'Unnamed Quest')}\n"
        return response.strip()

    if not active_quests: return "Your quest journal is empty."

    response = f"{FORMAT_TITLE}Active Quests{FORMAT_RESET}\n{'-'*20}\n\n"
    found_active = False
    sorted_active = sorted(active_quests.values(), key=lambda q: q.get("title", ""))
    
    for quest_data in sorted_active:
         if quest_data.get("state") in ["active", "ready_to_complete"]:
             found_active = True
             
             # Use manager helper
             objective = context["world"].quest_manager.get_active_objective(quest_data) or {}
             obj_type = objective.get("type", "unknown")
             
             title = quest_data.get("title", "Unnamed Quest")
             
             # Resolve Giver / Turn-In
             stages = quest_data.get("stages", [])
             idx = quest_data.get("current_stage_index", 0)
             turn_in_target = quest_data.get("giver_instance_id")
             if stages and idx < len(stages):
                 stage_target = stages[idx].get("turn_in_id")
                 if stage_target: turn_in_target = stage_target
             
             giver_npc = context["world"].get_npc(turn_in_target)
             giver_name = giver_npc.name if giver_npc else "Unknown"
             if turn_in_target == "quest_board": giver_name = context["world"].quest_board_name()
             
             response += f"{FORMAT_CATEGORY}{title}{FORMAT_RESET} (Report to: {giver_name})\n"
             state_display = quest_data.get("state", "unknown").replace('_', ' ').capitalize(); response += f"  Status: {state_display}\n"
             
             if obj_type == "kill": 
                 response += f"  Task: Defeat {objective.get('current_quantity', 0)}/{objective.get('required_quantity', '?')} {objective.get('target_name_plural', '?')} in {objective.get('location_hint', '?')}.\n"
             
             elif obj_type == "group_kill":
                 response += f"  Task: Hunt the following targets:\n"
                 targets = objective.get("targets", {})
                 for tid, t_data in targets.items():
                     t_name = t_data.get("name", "Enemies")
                     req = t_data.get("required", 1)
                     cur = t_data.get("current", 0)
                     status_col = FORMAT_SUCCESS if cur >= req else FORMAT_RESET
                     response += f"    - {status_col}{t_name}: {cur}/{req}{FORMAT_RESET}\n"

             elif obj_type == "fetch":
                  required_item_id = objective.get("item_id", ""); current_have = player.inventory.count_item(required_item_id)
                  response += f"  Task: Gather {current_have}/{objective.get('required_quantity', '?')} {objective.get('item_name_plural', '?')} (from {objective.get('source_enemy_name_plural', '?')} in {objective.get('location_hint', '?')}).\n"
             
             elif obj_type == "deliver":
                  package_instance_id = objective.get("item_instance_id", ""); has_package = player.inventory.find_item_by_id(package_instance_id) is not None
                  package_status = f"{FORMAT_HIGHLIGHT}(You have the package){FORMAT_RESET}" if has_package else f"{FORMAT_ERROR}(You don't have the package!){FORMAT_RESET}"
                  response += f"  Task: Deliver the {objective.get('item_to_deliver_name', '?')} to {objective.get('recipient_name', '?')} in {objective.get('recipient_location_description', '?')}. {package_status}\n"
             
             else: 
                  # Generic fallback
                  desc = objective.get("description")
                  if not desc and stages and idx < len(stages):
                      desc = stages[idx].get("description")
                  
                  response += f"  Task: {desc or 'Complete the objective.'}\n"
             
             if quest_data.get('state') == "ready_to_complete": response += f"  {FORMAT_HIGHLIGHT}Ready to turn in!{FORMAT_RESET}\n"
             response += "\n"

    if not found_active: return "You have no active quests."
    return response.strip()
