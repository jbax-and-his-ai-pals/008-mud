from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET, FORMAT_HIGHLIGHT
from engine.world.region_generator import RegionGenerator
from engine.config.config_world import DYNAMIC_REGION_DEFAULT_NUM_ROOMS
from engine.npcs.npc import NPC

def _find_npc_globally(world, npc_name: str):
    lower = npc_name.lower()
    exact = [n for n in world.npcs.values() if n.name.lower() == lower]
    return exact if exact else [n for n in world.npcs.values() if lower in n.name.lower()]

@command(
    "settime",
    [],
    "debug",
    "Set time.\nUsage: settime <hour> [minute] or <period>",
    entitlements=["operator.world.debug"],
)
def settime_handler(args, context):
    tm = context["game"].time_manager
    if not args: return "Usage: settime <val>"
    
    periods = {"dawn": 6, "day": 10, "dusk": 18, "night": 22}
    if args[0].lower() in periods:
        hour = periods[args[0].lower()]
        minute = 0
    else:
        try:
            hour = int(args[0])
            minute = int(args[1]) if len(args) > 1 else 0
        except (ValueError, KeyError): return "Invalid format."
    
    # Calculate absolute game time
    days = (tm.year - 1) * 360 + (tm.month - 1) * 30 + (tm.day - 1)
    mins = days * 1440 + hour * 60 + minute
    tm.initialize_time(float(mins * 60))
    
    # Reset NPC schedules
    for npc in context["world"].npcs.values():
        if npc.behavior_type == "scheduled":
            npc.schedule_destination = None
            npc.current_path = []
            
    return f"{FORMAT_SUCCESS}Time set to {hour:02d}:{minute:02d}.{FORMAT_RESET}"

@command(
    "setweather",
    [],
    "debug",
    "Set weather.\nUsage: setweather <type> [intensity]",
    entitlements=["operator.world.debug"],
)
def setweather_handler(args, context):
    wm = context["game"].weather_manager
    if not args: return "Usage: setweather <type> [intensity]"
    
    wtype = args[0].lower()
    if wtype not in wm.weather_chances["summer"]: return "Invalid type."
    
    wm.current_weather = wtype
    if len(args) > 1: wm.current_intensity = args[1].lower()
    return f"{FORMAT_SUCCESS}Weather set.{FORMAT_RESET}"

@command(
    "teleport",
    ["tp"],
    "debug",
    "Teleport.\nUsage: tp <reg> <rm> OR tp <npc>",
    entitlements=["operator.world.debug"],
)
def teleport_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not args: return "Usage: tp <target>"
    if not player:
        return "Player not found."
    
    # Try Region:Room match first
    if len(args) == 2:
        reg = world.get_region(args[0])
        if reg and reg.get_room(args[1]):
            player.current_region_id = args[0]
            player.current_room_id = args[1]
            
            # --- TRIGGER UPDATE ---
            msgs = []
            if world.quest_manager:
                quest_msgs = world.quest_manager.handle_room_entry(player)
                if quest_msgs: msgs.extend(quest_msgs)
            
            msg_str = "\n".join(msgs)
            return f"{FORMAT_SUCCESS}Teleported to {args[0]}:{args[1]}.{FORMAT_RESET}\n{msg_str}"

    name = " ".join(args)
    matches = _find_npc_globally(world, name)
    
    if not matches:
        return f"{FORMAT_ERROR}Could not find location or NPC named '{name}'.{FORMAT_RESET}"
        
    if len(matches) > 1: return f"Ambiguous: {', '.join([n.name for n in matches])}"
    
    target = matches[0]
    if not target.current_region_id: return "NPC location unknown."
    
    player.current_region_id = target.current_region_id
    player.current_room_id = target.current_room_id
    
    # --- TRIGGER UPDATE ---
    msgs = []
    if world.quest_manager:
        quest_msgs = world.quest_manager.handle_room_entry(player)
        if quest_msgs: msgs.extend(quest_msgs)

    msg_str = "\n".join(msgs)
    return f"{FORMAT_SUCCESS}Teleported to {target.name}.{FORMAT_RESET}\n{msg_str}"

@command("whereis", ["find"], "debug", "Find NPC.\nUsage: whereis <name>")
def whereis_handler(args, context):
    world = context["world"]
    if not args: return "Usage: whereis <name>"
    matches = _find_npc_globally(world, " ".join(args))
    if not matches: return "Not found."
    npc = matches[0]
    return f"{npc.name} is at {npc.current_region_id}:{npc.current_room_id}"

@command("census", [], "debug", "Show NPC counts.")
def census_handler(args, context):
    world = context["world"]
    player = context.get("player")
    counts = {}
    for npc in world.npcs.values():
        if npc.is_alive:
            rid = npc.current_region_id or "unknown"
            counts[rid] = counts.get(rid, 0) + 1
            
    msg = [f"{FORMAT_SUCCESS}World Census:{FORMAT_RESET}"]
    current_region_id = getattr(player, "current_region_id", None)
    for rid, count in sorted(counts.items()):
        marker = "<<" if rid == current_region_id else ""
        msg.append(f"{rid}: {count} {marker}")
    return "\n".join(msg)

@command(
    "genregion",
    [],
    "debug",
    "Generate region.\nUsage: genregion <theme> [rooms]",
    entitlements=["operator.world.debug"],
)
def genregion_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not player or not player.current_region_id or not player.current_room_id: return "Must be in world."
    if not args: return "Usage: genregion <theme> [rooms]"
    
    theme = args[0].lower()
    rooms = int(args[1]) if len(args) > 1 else DYNAMIC_REGION_DEFAULT_NUM_ROOMS
    
    gen = RegionGenerator(world)
    res = gen.generate_region(theme, rooms)
    if not res: return "Generation failed."
    
    reg, eid = res
    world.add_region(reg.obj_id, reg)
    
    current_region = world.get_region(player.current_region_id)
    cur = current_region.get_room(player.current_room_id) if current_region else None
    if cur:
        cur.exits["portal"] = f"{reg.obj_id}:{eid}"
    
    entry_room = reg.get_room(eid)
    if entry_room:
        entry_room.exits["portal"] = f"{player.current_region_id}:{player.current_room_id}"
    
    return f"{FORMAT_SUCCESS}Generated {reg.name}. Portal created.{FORMAT_RESET}"

@command(
    "close portal",
    [],
    "debug",
    "Close portal and destroy region.",
    entitlements=["operator.world.debug"],
)
def close_portal_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not player or not player.current_region_id or not player.current_room_id:
        return "Must be in world."
    current_region = world.get_region(player.current_region_id)
    room = current_region.get_room(player.current_room_id) if current_region else None
    if not room or "portal" not in room.exits: return "No portal here."
    
    dest = room.exits["portal"]
    rid, rmid = dest.split(":")
    
    if not rid.startswith("dynamic_"): return "Not a dynamic region."
    
    # Cleanup
    ids = [n.obj_id for n in world.npcs.values() if n.current_region_id == rid]
    for i in ids: del world.npcs[i]
    if rid in world.regions: del world.regions[rid]
    del room.exits["portal"]
    
    return f"{FORMAT_SUCCESS}Region destroyed.{FORMAT_RESET}"
