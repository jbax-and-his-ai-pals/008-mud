# engine/commands/debug/general.py
from engine.commands.command_system import command, registered_commands, command_groups
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE, FORMAT_CATEGORY

@command("refresh", ["restore", "r"], "debug", "Heals player, fills mana, and resets all cooldowns.", content_capability="magic")
def refresh_handler(args, context):
    p = context.get("player")
    if not p: return "Player not found."
    p.health = p.max_health
    p.runtime_state.magic.mana = p.runtime_state.magic.max_mana
    p.runtime_state.magic.cooldowns = {}
    p.last_attack_time = 0
    return f"{FORMAT_SUCCESS}Player restored and cooldowns reset.{FORMAT_RESET}"

@command("ignoreplayer", [], "debug", "Make hostile NPCs ignore the player.\nUsage: ignoreplayer <on|off>")
def ignoreplayer_handler(args, context):
    game = context["game"]
    if not args or args[0].lower() not in ["on", "off"]:
        current_status = "ON" if game.debug_ignore_player else "OFF"
        return f"Usage: ignoreplayer <on|off>\nCurrently: {current_status}"

    action = args[0].lower()
    game.debug_ignore_player = (action == "on")
    status_msg = "will now ignore you" if action == "on" else "will now engage you normally"
    return f"{FORMAT_SUCCESS}Hostiles {status_msg}.{FORMAT_RESET}"

@command("debug_commands", ["dbgcmd"], "debug", "Show all registered commands and their state.")
def debug_commands_handler(args, context):
    total_commands = len(registered_commands)
    unique_commands = len(set(cmd['handler'] for cmd in registered_commands.values()))
    
    response = f"{FORMAT_TITLE}===== Command Registry State ====={FORMAT_RESET}\n"
    response += f"Total Registered Names/Aliases: {FORMAT_HIGHLIGHT}{total_commands}{FORMAT_RESET}\n"
    response += f"Unique Command Functions: {FORMAT_HIGHLIGHT}{unique_commands}{FORMAT_RESET}\n\n"

    if not registered_commands:
        response += f"{FORMAT_ERROR}No commands are registered!{FORMAT_RESET}\n"
        return response

    response += f"{FORMAT_TITLE}Commands by Category:{FORMAT_RESET}\n"
    for category, commands_list in sorted(command_groups.items()):
        if not commands_list: continue
        unique_cmds_in_cat = sorted(list({cmd['name'] for cmd in commands_list}))
        response += f"  - {FORMAT_CATEGORY}{category.capitalize()}{FORMAT_RESET} ({len(unique_cmds_in_cat)} unique):\n"
        for cmd_name in unique_cmds_in_cat:
            response += f"    - {cmd_name}\n"
    
    return response

@command("testrefactor", ["testlock"], "debug", "Focused test for locking/unlocking mechanics.", content_capability="magic")
def test_refactor_handler(args, context):
    from engine.items.container import Container
    from engine.items.key import Key
    from engine.items.item import Item
    from engine.items.lockpick import Lockpick
    from engine.magic.spell_registry import load_spells_from_json, get_spell

    world = context["world"]
    player = context.get('player')
    if not player: return "Player not found."

    load_spells_from_json(world.content_root)
    key_id = "debug_key_999"
    k_success, k_msg = player.learn_spell("knock")
    al_success, al_msg = player.learn_spell("arcane_lock")

    loot = Item(name="Victory Token", description="You successfully unlocked it!", weight=0.1, value=1000)
    chest = Container(obj_id="debug_chest_999", name="Refactor Chest", description="Test chest.", locked=True, key_id=key_id, capacity=100, contents=[loot])
    key = Key(obj_id=key_id, name="Refactor Key", description="Opens the chest.", weight=0.1)
    lockpick = Lockpick(obj_id="debug_lockpick_01", name="debug lockpick", description="A flimsy tool.", weight=0.1)
    if not player.current_region_id or not player.current_room_id:
        return "Player location unavailable."

    existing_chest = world.find_item_in_room_for_player("Refactor Chest", player)
    if existing_chest:
        world.remove_item_instance_from_room(player.current_region_id, player.current_room_id, existing_chest)
    
    world.add_item_to_room(player.current_region_id, player.current_room_id, chest)
    player.inventory.add_item(key)
    player.inventory.add_item(lockpick)
    player.runtime_state.magic.mana = player.runtime_state.magic.max_mana

    msgs = [
        f"{FORMAT_TITLE}--- LOCK/UNLOCK TEST INITIALIZED ---{FORMAT_RESET}",
        f"1. Placed {FORMAT_HIGHLIGHT}Refactor Chest{FORMAT_RESET} (Locked).",
        f"2. Added {FORMAT_HIGHLIGHT}Refactor Key{FORMAT_RESET} and {FORMAT_HIGHLIGHT}debug lockpick{FORMAT_RESET}.",
        f"3. Learned 'Knock': {k_success}",
        f"4. Learned 'Arcane Lock': {al_success}",
        f"\nTry: use refactor key on chest, cast knock on chest, use lockpick on chest"
    ]
    return "\n".join(msgs)
