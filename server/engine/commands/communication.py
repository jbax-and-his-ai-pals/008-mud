from typing import Any, List

from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET

@command("say", ["'"], "interaction", "Say something to everyone in your current room.\nUsage: say <message>")
def say_command(args: List[str], context: Any) -> str:
    player = context.get('player')
    if not player:
        return "You cannot speak."
    if not player.is_alive:
        return f"{FORMAT_ERROR}You are dead and cannot speak.{FORMAT_RESET}"
    
    if not args:
        return "What do you want to say?"
        
    message = " ".join(args).strip()
    if not message:
        return "What do you want to say?"

    formatted_message = f"[[CYAN]]{player.name} says, \"{message}\"[[/]]"
    
    # Broadcast to room
    game = context.get('game')
    if game and hasattr(game, "broadcast_to_room"):
        game.broadcast_to_room(player.current_region_id, player.current_room_id, formatted_message, exclude_session_id=context.get('session_id'))
         
    return f"You say, \"{message}\""

@command("yell", ["shout", "ooc"], "interaction", "Yell something to everyone on the server.\nUsage: yell <message>")
def yell_command(args: List[str], context: Any) -> str:
    player = context.get('player')
    if not player:
        return "You cannot speak."
    if not player.is_alive:
        return f"{FORMAT_ERROR}You are dead and cannot speak.{FORMAT_RESET}"
    
    if not args:
        return "What do you want to yell?"
        
    message = " ".join(args).strip()
    if not message:
        return "What do you want to yell?"

    formatted_message = f"[[YELLOW]]{player.name} yells, \"{message}\"[[/]]"
    
    # Broadcast globally
    game = context.get('game')
    if game and hasattr(game, "broadcast_global"):
        game.broadcast_global(formatted_message, exclude_session_id=context.get('session_id'))
         
    return f"You yell, \"{message}\""
