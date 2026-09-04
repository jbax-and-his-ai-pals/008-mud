# engine/commands/debug/quests.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE, FORMAT_CATEGORY

@command("quest", ["qdebug"], "debug", "Manage quests.\nUsage: quest list | quest advance <id> | quest complete <id>")
def quest_debug_handler(args, context):
    world = context["world"]
    player = context.get('player')
    qm = world.quest_manager
    
    if not args: return f"{FORMAT_ERROR}Usage: quest list | advance <id> | complete <id>{FORMAT_RESET}"
    
    sub = args[0].lower()
    
    if sub == "list":
        if not player.runtime_state.quests.active: return "No active quests."
        msg = [f"{FORMAT_TITLE}ACTIVE QUESTS (Debug Info){FORMAT_RESET}"]
        for qid, qdata in player.runtime_state.quests.active.items():
            state = qdata.get("state")
            stage = qdata.get("current_stage_index", 0)
            msg.append(f"- {FORMAT_HIGHLIGHT}{qid}{FORMAT_RESET} [{state}] (Stage {stage})")
        return "\n".join(msg)

    if len(args) < 2: return "Usage: quest <action> <quest_id>"
    
    search_id = args[1].lower()
    target_id = None
    for qid in player.runtime_state.quests.active.keys():
        if search_id in qid.lower():
            target_id = qid; break
            
    if not target_id: return f"{FORMAT_ERROR}Quest '{search_id}' not found in active log.{FORMAT_RESET}"
    
    if sub == "advance":
        result = qm.advance_quest_stage(player, target_id)
        if result == "QUEST_COMPLETE":
             return quest_debug_handler(["complete", target_id], context)
        return f"{FORMAT_SUCCESS}Forced advancement of {target_id}.{FORMAT_RESET}\nNPC Says: \"{result}\""

    if sub == "complete":
        res_msg = qm.complete_quest(player, target_id, resolution="SUCCESS")
        return f"{FORMAT_SUCCESS}Forced completion of {target_id}.{FORMAT_RESET}\n{res_msg}"
        
    return "Unknown subcommand."

@command("campaign", ["saga", "cdebug"], "debug", "Manage campaigns.\nUsage: campaign list | start <id> | jump <camp_id> <node_id>")
def campaign_debug_handler(args, context):
    world = context["world"]
    player = context.get('player')
    cm = world.campaign_manager
    
    if not args: return f"{FORMAT_ERROR}Usage: campaign list | start <id> | jump <camp_id> <node_id>{FORMAT_RESET}"
    sub = args[0].lower()
    
    if sub == "list":
        msg = [f"{FORMAT_TITLE}CAMPAIGNS{FORMAT_RESET}"]
        msg.append(f"{FORMAT_CATEGORY}Active:{FORMAT_RESET}")
        if not player.runtime_state.quests.active_campaigns: msg.append("  (None)")
        for cid, state in player.runtime_state.quests.active_campaigns.items():
            msg.append(f"  - {FORMAT_HIGHLIGHT}{cid}{FORMAT_RESET}: Node '{state.get('current_node')}'")
        msg.append(f"\n{FORMAT_CATEGORY}Available Definitions:{FORMAT_RESET}")
        for cid in cm.definitions.keys():
            msg.append(f"  - {cid}")
        return "\n".join(msg)
        
    if sub == "start":
        if len(args) < 2: return "Usage: campaign start <campaign_id>"
        cid = args[1]
        if cm.start_campaign(cid, player):
            return f"{FORMAT_SUCCESS}Started campaign '{cid}'.{FORMAT_RESET}"
        return f"{FORMAT_ERROR}Failed to start '{cid}'.{FORMAT_RESET}"

    if sub == "jump":
        if len(args) < 3: return "Usage: campaign jump <campaign_id> <node_id>"
        cid, node_id = args[1], args[2]
        if cid not in player.runtime_state.quests.active_campaigns: return f"{FORMAT_ERROR}Campaign '{cid}' is not active.{FORMAT_RESET}"
        defn = cm.definitions.get(cid)
        if not defn or node_id not in defn.nodes: return f"{FORMAT_ERROR}Node '{node_id}' not found.{FORMAT_RESET}"
        
        player.runtime_state.quests.active_campaigns[cid]["current_node"] = node_id
        cm._trigger_node(cid, defn.nodes[node_id], player)
        return f"{FORMAT_SUCCESS}Jumped campaign '{cid}' to node '{node_id}'.{FORMAT_RESET}"

    return "Unknown subcommand."
