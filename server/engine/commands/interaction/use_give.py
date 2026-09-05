# engine/commands/interaction/use_give.py
import time
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, USE_COMMAND_PREPOSITIONS, GIVE_COMMAND_PREPOSITION
from engine.items.consumable import Consumable
from engine.items.key import Key

@command("use", ["activate", "drink", "eat", "apply"], "interaction", "Use an item.\nUsage: use <item> [on <target>]")
def use_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Use what?{FORMAT_RESET}"

    prep_idx = -1
    for i, w in enumerate(args):
        if w.lower() in USE_COMMAND_PREPOSITIONS: prep_idx = i; break
        
    if prep_idx != -1:
        item_name = " ".join(args[:prep_idx]).lower()
        target_name = " ".join(args[prep_idx+1:]).lower()
    else:
        item_name = " ".join(args).lower()
        target_name = None

    item = player.inventory.find_item_by_name(item_name)
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"

    target = None
    if target_name:
        target = (
            world.find_item_in_room_for_player(target_name, player)
            or player.inventory.find_item_by_name(target_name, exclude=item)
            or world.find_npc_in_room_for_player(target_name, player)
        )
        if not target and target_name in ["self", "me"]: target = player
        if not target: return f"{FORMAT_ERROR}Target '{target_name}' not found.{FORMAT_RESET}"
    
    # Validation for Keys
    if isinstance(item, Key) and not target:
         return f"{FORMAT_ERROR}Use key on what?{FORMAT_RESET}"

    try:
        # Some use() methods don't take target kwarg, some do. 
        # Base Item.use accepts **kwargs.
        if target:
             res = item.use(user=player, target=target)
        else:
             res = item.use(user=player)

        # Consumable Logic
        if isinstance(item, Consumable) and item.get_property("uses", 1) <= 0:
             player.inventory.remove_item(item.obj_id)

        return f"{FORMAT_HIGHLIGHT}{res}{FORMAT_RESET}"

    except Exception as e:
        return f"{FORMAT_ERROR}Failed to use item: {e}{FORMAT_RESET}"

@command("give", [], "interaction", "Give item to NPC.\nUsage: give <item> to <npc>")
def give_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    
    if GIVE_COMMAND_PREPOSITION not in [a.lower() for a in args]:
        return f"{FORMAT_ERROR}Usage: give <item> {GIVE_COMMAND_PREPOSITION} <npc>{FORMAT_RESET}"
    
    try:
        idx = [a.lower() for a in args].index(GIVE_COMMAND_PREPOSITION)
        item_name = " ".join(args[:idx]).lower()
        npc_name = " ".join(args[idx+1:]).lower()
    except (ValueError, AttributeError): return f"{FORMAT_ERROR}Parse error.{FORMAT_RESET}"

    item = player.inventory.find_item_by_name(item_name)
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"
    
    npc = world.find_npc_in_room_for_player(npc_name, player)
    if not npc: return f"{FORMAT_ERROR}NPC '{npc_name}' not found.{FORMAT_RESET}"

    # Quest Delivery Logic
    matching_quest = None

    quests_active = player.runtime_state.quests.active if player.runtime_state.quests is not None else {}
    for q_id, q_data in quests_active.items():
        if q_data.get("state") != "active": continue
        
        qm = world.quest_manager
        objective = qm.get_active_objective(q_data) or q_data.get("objective", {})
        
        if (objective.get("type") == "deliver" and 
            objective.get("item_instance_id") == item.obj_id):
            
            # Found item match, check recipient
            if objective.get("recipient_instance_id") == npc.obj_id:
                matching_quest = (q_id, q_data)
                break
            else:
                # Wrong recipient for quest item
                return f"{FORMAT_ERROR}You should give the {item.name} to {objective.get('recipient_name', 'someone else')}, not {npc.name}.{FORMAT_RESET}"

    if matching_quest:
        # It's a quest delivery!
        quest_id, quest_data = matching_quest
        
        # Remove item
        rem_item, count, _ = player.inventory.remove_item(item.obj_id, 1)
        if not rem_item: return f"{FORMAT_ERROR}Failed to remove item.{FORMAT_RESET}"
        
        # Complete Quest
        qm = world.quest_manager
        rewards_msg = qm.complete_quest(player, quest_id)
        
        npc_response = npc.dialog.get(f"complete_{quest_id}", npc.dialog.get("quest_complete", "Thank you!"))
        
        msg = f"{FORMAT_SUCCESS}[Quest Complete] {quest_data.get('title')}{FORMAT_RESET}\n"
        msg += f"{FORMAT_HIGHLIGHT}\"{npc_response}\"{FORMAT_RESET}\n"
        if rewards_msg: msg += rewards_msg
        
        return msg
        
    else:
        # Standard Gift
        rem_item, count, _ = player.inventory.remove_item(item.obj_id, 1)
        if rem_item:
            # Add to NPC inventory if possible
            if hasattr(npc, 'inventory'):
                npc.inventory.add_item(rem_item)
            return f"{FORMAT_SUCCESS}You give the {rem_item.name} to {npc.name}.{FORMAT_RESET}"
        return f"{FORMAT_ERROR}Failed to remove item.{FORMAT_RESET}"
