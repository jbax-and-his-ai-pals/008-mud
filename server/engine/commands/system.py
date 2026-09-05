# engine/commands/system.py
"""
Contains all core system and meta-game commands.
"""
import os
from engine.commands.command_system import command
from engine.config import SAVE_GAME_DIR, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS
from engine.config.config_display import FORMAT_TITLE

@command("help", ["h", "?"], "system", "Show help.\nUsage: help [command]")
def help_handler(args, context):
    cp = context["command_processor"]
    world = context.get("world")
    return (
        cp.get_command_help(args[0], world)
        if args
        else cp.get_help_text(world)
    )

@command("stop", [], "system", "Stop a current automated action, like being guided.\nUsage: stop")
def stop_handler(args, context):
    game = context.get("game")
    if game and game.is_auto_traveling:
        game.stop_auto_travel("cancelled")
        return "" # The stop_auto_travel function will print its own message
    return "There is nothing to stop."

# "exit" is intentionally not an alias here -- the dynamically-registered
# "out" movement command already owns that word (and registers after every
# static module, including this one), so it silently wins over this one.
@command("quit", ["q"], "system", "Return to the main title screen.")
def quit_handler(args, context):
    game = context.get("game")
    if game:
        game.quit_to_title()
        return f"{FORMAT_HIGHLIGHT}Returning to title screen...{FORMAT_RESET}"
    return f"{FORMAT_ERROR}Game context not found.{FORMAT_RESET}"

@command("save", [], "system", "Save game state.\nUsage: save [filename]")
def save_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    game = context["game"]
    fname = (args[0] if args else game.current_save_file)
    if not fname.endswith(".json"): fname += ".json"
    if world.save_game(fname):
        game.current_save_file = fname
        return f"{FORMAT_SUCCESS}World state saved to {fname}{FORMAT_RESET}"
    else:
        return f"{FORMAT_ERROR}Error saving world state to {fname}{FORMAT_RESET}"

@command("load", [], "system", "Load game state.\nUsage: load [filename]")
def load_handler(args, context):
    world = context["world"]
    game = context["game"]
    fname = (args[0] if args else game.current_save_file)
    if not fname.endswith(".json"): fname += ".json"
    save_path = os.path.join(SAVE_GAME_DIR, fname)
    if not os.path.exists(save_path):
         return f"{FORMAT_ERROR}Save file '{fname}' not found in '{SAVE_GAME_DIR}'.{FORMAT_RESET}"
    
    print(f"Attempting to load game state from {fname}...")
    
    load_success, loaded_time_data, loaded_weather_data = world.load_save_game(fname)
    
    if load_success:
         game.current_save_file = fname
         
         # Apply loaded states to core managers
         game.time_manager.apply_loaded_time_state(loaded_time_data)
         game.weather_manager.apply_loaded_weather_state(loaded_weather_data)
         
         # Reset UI and input state if they exist
         renderer = getattr(game, "renderer", None)
         if renderer:
             if hasattr(renderer, "text_buffer"): renderer.text_buffer = []
             if hasattr(renderer, "scroll_offset"): renderer.scroll_offset = 0
             
         input_handler = getattr(game, "input_handler", None)
         if input_handler:
             if hasattr(input_handler, "input_text"): input_handler.input_text = ""
             if hasattr(input_handler, "command_history"): input_handler.command_history = []
             if hasattr(input_handler, "history_index"): input_handler.history_index = -1
         
         game.game_state = "playing"
         
         return f"{FORMAT_SUCCESS}World state loaded from {fname}{FORMAT_RESET}\n\n{world.look()}"
    else:
         return f"{FORMAT_ERROR}Error loading world state from {fname}. Game state might be unstable.{FORMAT_RESET}"

@command("minimap", ["map"], "system", "Toggle the visual minimap panel.\nUsage: minimap [on|off]")
def toggle_minimap_handler(args, context):
    game = context.get("game")
    if not game: return f"{FORMAT_ERROR}System error: Game context missing.{FORMAT_RESET}"
    
    panel_id = "map"
    manager = getattr(game, "ui_manager", None)
    if not manager:
        return f"{FORMAT_ERROR}UI commands are not available in this environment.{FORMAT_RESET}"
    
    # Check if currently visible
    is_visible = False
    for panel in manager.right_dock + manager.left_dock:
        if panel.panel_id == panel_id:
            is_visible = True
            break

    should_show = not is_visible # Default toggle logic

    if args:
        arg = args[0].lower()
        if arg == "on": should_show = True
        elif arg == "off": should_show = False
        else: return f"{FORMAT_ERROR}Usage: minimap [on|off]{FORMAT_RESET}"

    if should_show:
        if is_visible:
            return f"{FORMAT_HIGHLIGHT}Minimap is already enabled.{FORMAT_RESET}"
        
        # Try adding to right dock
        if manager.add_panel_to_dock(panel_id, "right"):
             return f"{FORMAT_SUCCESS}Minimap enabled.{FORMAT_RESET}"
        else:
             return f"{FORMAT_ERROR}Could not enable minimap (Panel ID error).{FORMAT_RESET}"
    else:
        if not is_visible:
            return f"{FORMAT_HIGHLIGHT}Minimap is already disabled.{FORMAT_RESET}"
            
        if manager.remove_panel(panel_id):
            return f"{FORMAT_SUCCESS}Minimap disabled.{FORMAT_RESET}"
        else:
            return f"{FORMAT_ERROR}Could not disable minimap.{FORMAT_RESET}"
    
@command("view", ["ui", "panel"], "system", "Manage UI panels.\nUsage: view list | view <panel> <on|off>")
def view_panel_handler(args, context):
    game = context.get("game")
    if not game: return "Error: Game context missing."
    manager = getattr(game, "ui_manager", None)
    if not manager:
        return f"{FORMAT_ERROR}UI commands are not available in this environment.{FORMAT_RESET}"
    
    if not args:
        return f"{FORMAT_ERROR}Usage: view list | view <panel_id> <on|off>{FORMAT_RESET}"

    subcmd = args[0].lower()
    
    if subcmd == "list":
        msg = [f"{FORMAT_TITLE}Available UI Panels:{FORMAT_RESET}"]
        for pid, panel in manager.all_panels_registry.items():
            state = "Hidden"
            if panel in manager.left_dock: state = f"{FORMAT_SUCCESS}Left Dock{FORMAT_RESET}"
            elif panel in manager.right_dock: state = f"{FORMAT_SUCCESS}Right Dock{FORMAT_RESET}"
            
            msg.append(f"- {FORMAT_HIGHLIGHT}{pid:<12}{FORMAT_RESET}: {state}")
        return "\n".join(msg)
    
    if len(args) < 2:
        return f"{FORMAT_ERROR}Usage: view <panel_id> <on|off>{FORMAT_RESET}"
        
    panel_id = subcmd
    action = args[1].lower()
    
    if panel_id not in manager.all_panels_registry:
        return f"{FORMAT_ERROR}Unknown panel '{panel_id}'. Type 'view list' to see options.{FORMAT_RESET}"
        
    if action == "on":
        # Default to right dock if adding new, or left? let's default right for now or specific logic
        # Logic: Try to add to right dock by default if not present
        if manager.add_panel_to_dock(panel_id, "right"):
            return f"{FORMAT_SUCCESS}Panel '{panel_id}' enabled (added to right dock).{FORMAT_RESET}"
        else:
            return f"Panel '{panel_id}' is already visible."
            
    elif action == "off":
        if manager.remove_panel(panel_id):
            return f"{FORMAT_SUCCESS}Panel '{panel_id}' hidden.{FORMAT_RESET}"
        else:
            return f"Panel '{panel_id}' is already hidden."
            
    return f"{FORMAT_ERROR}Invalid action '{action}'. Use 'on' or 'off'.{FORMAT_RESET}"

@command(
    "toggle",
    [],
    "system",
    "Toggle a server feature mode.\nUsage: toggle <category> <value>",
    capabilities=["authoring.gm"],
    entitlements=["operator.feature_profile.toggle"],
)
def toggle_handler(args, context):
    game = context.get("game")
    if not game: return f"{FORMAT_ERROR}Game context not found.{FORMAT_RESET}"
    
    if len(args) < 2:
        return f"{FORMAT_ERROR}Usage: toggle <category> <value>\nExample: toggle permadeath enabled{FORMAT_RESET}"
        
    category = args[0].lower()
    value = args[1].lower()
    
    success, msg = game.feature_profile.set_mode(category, value)
    if success:
        game.broadcast_global(f"[[YELLOW]]SERVER:[[/]] {msg}")
        return f"{FORMAT_SUCCESS}{msg}{FORMAT_RESET}"
    else:
        return f"{FORMAT_ERROR}{msg}{FORMAT_RESET}"
