# engine/commands/command_system.py
from typing import Callable, List, Dict, Any, Optional, Set
from functools import wraps
import inspect

from engine.config import FORMAT_CATEGORY, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_TITLE, HELP_MAX_COMMANDS_PER_CATEGORY

# Dictionary to store all registered commands
registered_commands: Dict[str, Dict[str, Any]] = {}
command_groups: Dict[str, List[Dict[str, Any]]] = {
    "movement": [], "interaction": [], "inventory": [],
    "combat": [], "magic": [], "system": [], "other": []
}

# Direction aliases for movement commands
direction_aliases = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "u": "up", "d": "down"
}

def command(name: str, aliases: Optional[List[str]] = None, category: str = "other",
           help_text: str = "No help available.", plugin_id: Optional[str] = None,
           capabilities: Optional[List[str]] = None,
           entitlements: Optional[List[str]] = None,
           content_capability: Optional[str] = None,
           ruleset_system: Optional[str] = None):
    """
    Decorator for registering game commands.
    """
    # Use idiomatic default for optional list
    aliases = aliases or []

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._command_info = { # type: ignore
            "name": name,
            "aliases": aliases,
            "category": category,
            "help_text": help_text,
            "plugin_id": plugin_id
        }
        
        cmd_data = {
            "name": name,
            "aliases": aliases,
            "handler": wrapper,
            "help_text": help_text,
            "category": category,
            "plugin_id": plugin_id,
            "capabilities": capabilities or [],
            # Optional entitlement gate names required to execute this command.
            "entitlements": entitlements or [],
            # Optional game-system requirement, chosen by a content set rather
            # than granted to an individual session.
            "content_capability": content_capability,
            "ruleset_system": ruleset_system,
        }
        
        registered_commands[name] = cmd_data
        for alias in aliases:
            registered_commands[alias] = cmd_data
            
        if category in command_groups:
            command_groups[category].append(cmd_data)
        else:
            # Create category if it doesn't exist (useful for plugins)
            command_groups.setdefault(category, []).append(cmd_data)
        
        return wrapper
    return decorator

def get_registered_commands() -> Dict[str, Dict[str, Any]]:
    """Get all registered commands."""
    return registered_commands

def get_command_groups() -> Dict[str, List[Dict[str, Any]]]:
    """Get commands organized by category."""
    return command_groups

def unregister_command(name: str) -> bool:
    """Unregister a command and all its aliases."""
    if name not in registered_commands:
        return False
        
    cmd_data = registered_commands[name]
    cmd_name = cmd_data["name"]
    cmd_aliases = cmd_data["aliases"]
    cmd_category = cmd_data["category"]
    
    # Remove from main dictionary by primary name
    if cmd_name in registered_commands:
        del registered_commands[cmd_name]
    
    # Remove all aliases
    for alias in cmd_aliases:
        if alias in registered_commands:
            del registered_commands[alias]
    
    # Remove from category group
    if cmd_category in command_groups:
        command_groups[cmd_category] = [c for c in command_groups[cmd_category] if c["name"] != cmd_name]
    
    return True

def unregister_plugin_commands(plugin_id: str) -> int:
    """Unregister all commands registered by a specific plugin."""
    if not plugin_id: return 0
        
    # Find all primary command names associated with this plugin
    plugin_command_names = [
        cmd_data["name"] for cmd_data in registered_commands.values()
        if cmd_data.get("plugin_id") == plugin_id
    ]
    # Use a set to avoid unregistering the same command multiple times
    unique_names_to_unregister = set(plugin_command_names)
    
    count = 0
    for cmd_name in unique_names_to_unregister:
        if unregister_command(cmd_name):
            count += 1
    
    return count

class CommandProcessor:
    """Processes user input and dispatches commands to appropriate handlers."""

    @staticmethod
    def resolve_command(text: str) -> tuple[Dict[str, Any] | None, List[str]]:
        """Resolve text using the same longest-match rule used for dispatch."""
        parts = str(text).strip().lower().split()
        for index in range(len(parts), 0, -1):
            command_key = " ".join(parts[:index])
            command_key = direction_aliases.get(command_key, command_key)
            if command_key in registered_commands:
                return registered_commands[command_key], parts[index:]
        return None, []

    def content_block_reason(self, text: str, world: Any) -> str:
        """Return a package-level rejection for a registered unavailable command."""
        command_data, _args = self.resolve_command(text)
        if command_data is None or self._is_content_enabled(command_data, world):
            return ""
        required_capability = command_data.get("content_capability")
        if required_capability and not world.has_capability(required_capability):
            return f"This game does not include the '{required_capability}' system."
        required_system = command_data.get("ruleset_system")
        if required_system and not world.ruleset_system_enabled(required_system):
            return f"This game does not include the '{required_system}' system."
        return "This command is not available in this game."

    def process_input(self, text: str, context: Any = None) -> str:
        """
        Process user input and execute the corresponding command using a
        longest-match-first strategy for multi-word commands.
        """
        text = text.strip().lower()
        if not text: return ""
        parts = text.split()
        
        # --- NEW: Longest-Match Parsing Logic ---
        # Iterate from the longest possible command phrase down to a single word.
        cmd_data, args = self.resolve_command(text)
        if cmd_data is not None:
            # Add context for the handler.
            if context and isinstance(context, dict):
                context['executed_command_name'] = cmd_data.get('name', '')
                context['executed_command_aliases'] = cmd_data.get('aliases', [])

                if "authz_hook" in context:
                    if not context["authz_hook"](cmd_data):
                        return f"{FORMAT_ERROR}You do not have permission to use this command.{FORMAT_RESET}"

            return cmd_data["handler"](args, context)

        # Content can author contextual exit verbs (for example, "house"
        # or "hatch") without adding them to the process-global command
        # registry. Prefer registered commands, then let a one-word unknown
        # command move through a same-named exit in the player's current room.
        if context and isinstance(context, dict) and len(parts) == 1:
            world = context.get("world")
            player = context.get("player")
            room = world.get_current_room(player) if world is not None and player is not None else None
            if room is not None and parts[0] in getattr(room, "exits", {}):
                if not getattr(player, "is_alive", True):
                    return f"{FORMAT_ERROR}You are dead. You cannot move.{FORMAT_RESET}"
                if getattr(player, "trading_with", None):
                    vendor = world.get_npc(player.trading_with)
                    if vendor:
                        vendor.is_trading = False
                    player.trading_with = None
                return world.change_room(parts[0], player=player)

        # No registered command matches this input.
        return f"{FORMAT_ERROR}Unknown command: {parts[0]}{FORMAT_RESET}"

    def get_help_text(self, world: Any = None) -> str:
        """Generate the top-level help text showing categories and commands."""
        help_text = f"{FORMAT_TITLE}===== Help ====={FORMAT_RESET}\n\n"
        help_text += "Interact by typing commands. Use the following categories for guidance:\n\n"
        help_text += f"{FORMAT_HIGHLIGHT}How to Get More Help:{FORMAT_RESET}\n"
        help_text += f"  - Type '{FORMAT_HIGHLIGHT}help <category>{FORMAT_RESET}' for all commands in a category.\n"
        help_text += f"  - Type '{FORMAT_HIGHLIGHT}help <command>{FORMAT_RESET}' for details on a specific command.\n\n"
        help_text += f"{FORMAT_TITLE}Command Categories & Examples:{FORMAT_RESET}\n"

        # "debug"/GM-only tooling is intentionally left off the discoverable
        # overview -- it still works if invoked directly (help <category>
        # or the command itself), it's just not advertised to every player.
        categories = sorted([
            category for category, commands in command_groups.items()
            if category != "debug" and any(self._is_content_enabled(command_data, world) for command_data in commands)
        ])
        max_cmds_to_show = HELP_MAX_COMMANDS_PER_CATEGORY

        for category in categories:
            commands_in_category = [
                command_data for command_data in command_groups[category]
                if self._is_content_enabled(command_data, world)
            ]
            unique_primary_names = sorted(list({cmd['name'] for cmd in commands_in_category}))
            command_list_str = ""
            if unique_primary_names:
                if len(unique_primary_names) > max_cmds_to_show:
                    command_list_str = ", ".join(unique_primary_names[:max_cmds_to_show]) + ", ..."
                else:
                    command_list_str = ", ".join(unique_primary_names)
            help_text += f"  - {FORMAT_CATEGORY}{category.capitalize()}{FORMAT_RESET}"
            if command_list_str:
                help_text += f" ({FORMAT_HIGHLIGHT}{command_list_str}{FORMAT_RESET})\n"
            else:
                help_text += "\n"
        help_text += "\n"
        
        help_text += f"{FORMAT_TITLE}Getting Started Examples:{FORMAT_RESET}\n"
        help_text += f"  - {FORMAT_HIGHLIGHT}look{FORMAT_RESET}\n"
        help_text += f"  - {FORMAT_HIGHLIGHT}north{FORMAT_RESET} (or {FORMAT_HIGHLIGHT}n{FORMAT_RESET})\n"
        help_text += f"  - {FORMAT_HIGHLIGHT}take <item>{FORMAT_RESET}\n"
        help_text += f"  - {FORMAT_HIGHLIGHT}inventory{FORMAT_RESET}\n\n"
        help_text += f"{FORMAT_TITLE}Other Tips:{FORMAT_RESET}\n"
        help_text += "  - Use Up/Down arrows for command history.\n"
        help_text += "  - Use Tab for command/category completion.\n"
        help_text += "  - Use PageUp/PageDown/Mouse Wheel to scroll text.\n"

        return help_text
    
    def get_command_help(
        self,
        command_or_category_name: str,
        world: Any = None,
    ) -> str:
        """Get detailed help for a specific command OR a category."""
        name_lower = command_or_category_name.lower()

        if name_lower in command_groups and command_groups[name_lower]:
            return self._get_category_help(name_lower, world)

        if name_lower in direction_aliases:
            name_lower = direction_aliases[name_lower]

        if name_lower in registered_commands:
            cmd = registered_commands[name_lower]
            if not self._is_content_enabled(cmd, world):
                return f"{FORMAT_ERROR}No help found for '{command_or_category_name}'. It is not available in this game.{FORMAT_RESET}"
            help_text = f"{FORMAT_TITLE}Command: {cmd['name'].upper()}{FORMAT_RESET}\n\n"
            help_text += f"{FORMAT_CATEGORY}Category:{FORMAT_RESET} {cmd['category'].capitalize()}\n"
            if cmd['aliases']:
                help_text += f"{FORMAT_CATEGORY}Aliases:{FORMAT_RESET} {', '.join(cmd['aliases'])}\n"
            help_text += f"\n{FORMAT_CATEGORY}Description:{FORMAT_RESET}\n"
            for line in cmd['help_text'].split('\n'):
                help_text += f"  {line}\n"
            return help_text

        return f"{FORMAT_ERROR}No help found for '{command_or_category_name}'. It is not a valid command or category.{FORMAT_RESET}\nType '{FORMAT_HIGHLIGHT}help{FORMAT_RESET}' for available categories."
    
    def get_command_suggestions(self, partial_command: str) -> List[str]:
        """Get a list of commands that start with the given partial command."""
        partial = partial_command.lower()
        suggestions = set()

        for cmd_name, cmd_data in registered_commands.items():
            primary_name = cmd_data['name']
            if primary_name.startswith(partial): suggestions.add(primary_name)
            for alias in cmd_data.get('aliases', []):
                 if alias.startswith(partial): suggestions.add(alias)
        for alias, direction in direction_aliases.items():
            if alias.startswith(partial): suggestions.add(alias)
        for category_name in command_groups.keys():
             if category_name.startswith(partial): suggestions.add(category_name)

        return sorted(list(suggestions))

    @staticmethod
    def _is_content_enabled(command_data: Dict[str, Any], world: Any = None) -> bool:
        """Return whether this command is enabled by the loaded game contract."""
        if world is None:
            return True
        required_capability = command_data.get("content_capability")
        if required_capability and not world.has_capability(required_capability):
            return False
        required_system = command_data.get("ruleset_system")
        return not required_system or world.ruleset_system_enabled(required_system)

    def _get_category_help(
        self,
        category_name: str,
        world: Any = None,
    ) -> str:
        """Generate help text for a specific command category."""
        category_name_lower = category_name.lower()
        commands_in_category = [
            command_data for command_data in command_groups[category_name_lower]
            if self._is_content_enabled(command_data, world)
        ]
        help_text = f"{FORMAT_TITLE}Help: {category_name.capitalize()} Commands{FORMAT_RESET}\n\n"
        
        unique_commands = {}
        for cmd in commands_in_category:
            handler_id = id(cmd["handler"])
            if handler_id not in unique_commands:
                unique_commands[handler_id] = cmd
        
        sorted_unique_commands = sorted(unique_commands.values(), key=lambda c: c["name"])
        for cmd in sorted_unique_commands:
            aliases = f" ({', '.join(cmd['aliases'])})" if cmd['aliases'] else ""
            first_line_help = cmd['help_text'].split('\n')[0]
            help_text += f"  {FORMAT_HIGHLIGHT}{cmd['name']}{aliases}{FORMAT_RESET}\n"
            help_text += f"    - {first_line_help}\n"
        help_text += f"\nType '{FORMAT_HIGHLIGHT}help <command>{FORMAT_RESET}' for more details on a specific command."
        return help_text
