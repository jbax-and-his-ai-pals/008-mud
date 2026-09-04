# engine/commands/inventory.py
"""
Contains all commands related to the player's inventory and equipment.
"""
from engine.commands.command_system import command
from engine.config import EQUIP_COMMAND_SLOT_PREPOSITION, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_SUCCESS, FORMAT_TITLE, FORMAT_RESET
from engine.items.item import Item
from engine.items.weapon import Weapon
from engine.items.consumable import Consumable
from engine.items.container import Container
from engine.items.junk import Junk
from engine.items.key import Key
from engine.utils.utils import get_article, simple_plural

@command("inventory", ["i", "inv"], "inventory", "Show items you are carrying (Text).", content_capability="inventory")
def inventory_handler(args, context):
    """Standard text-based inventory listing."""
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    # Text output remains available for accessibility and terminal clients.
    inventory_text = f"{FORMAT_TITLE}INVENTORY{FORMAT_RESET}\n\n"
    inventory_text += player.inventory.list_items()
    # ...
    return inventory_text 

@command("invmode", [], "inventory", "Change visual inventory display mode.\nUsage: invmode <text|icon|hybrid>", content_capability="inventory")
def invmode_handler(args, context):
    game = context["game"]
    if not args:
        return f"Current mode: {game.inventory_mode}. Usage: invmode <text|icon|hybrid>"
    
    mode = args[0].lower()
    if mode in ["text", "icon", "hybrid"]:
        game.inventory_mode = mode
        return f"{FORMAT_SUCCESS}Visual Inventory mode set to {mode}.{FORMAT_RESET}"
    else:
        return f"{FORMAT_ERROR}Invalid mode. Options: text, icon, hybrid{FORMAT_RESET}"

@command("status", ["stat", "st"], "inventory", "Display character status.")
def status_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    return player.get_status()

@command("equip", ["wear", "wield"], "inventory", "Equip an item from your inventory.\nUsage: equip <item_name> [to <slot_name>]", content_capability="inventory")
def equip_handler(args, context):
    player = context["world"].player
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot equip items.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}What do you want to equip?{FORMAT_RESET}"
    item_name = ""; slot_name = None
    if EQUIP_COMMAND_SLOT_PREPOSITION in [a.lower() for a in args]:
        try:
            to_index = [a.lower() for a in args].index(EQUIP_COMMAND_SLOT_PREPOSITION)
            item_name = " ".join(args[:to_index]).lower()
            slot_name = " ".join(args[to_index + 1:]).lower().replace(" ", "_")
        except ValueError: item_name = " ".join(args).lower()
    else: item_name = " ".join(args).lower()
    item_to_equip = player.inventory.find_item_by_name(item_name)
    if not item_to_equip: return f"{FORMAT_ERROR}You don't have '{item_name}' in your inventory.{FORMAT_RESET}"
    success, message = player.equip_item(item_to_equip, slot_name)
    return f"{FORMAT_SUCCESS}{message}{FORMAT_RESET}" if success else f"{FORMAT_ERROR}{message}{FORMAT_RESET}"

@command("unequip", ["remove"], "inventory", "Unequip an item by name or slot.\nUsage: unequip <item_name | slot_name>", content_capability="inventory")
def unequip_handler(args, context):
    player = context["world"].player
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead. You cannot unequip items.{FORMAT_RESET}"
    
    if not args:
        equipped_text = f"{FORMAT_TITLE}EQUIPPED ITEMS{FORMAT_RESET}\n"
        has_equipped = False
        for slot, item in player.equipment.items():
            if item:
                equipped_text += f"- {slot.replace('_', ' ').capitalize()}: {item.name}\n"
                has_equipped = True
        if not has_equipped: equipped_text += "  (Nothing equipped)\n"
        equipped_text += "\nUsage: unequip <item_name | slot_name>"
        return equipped_text

    identifier = " ".join(args).lower()
    slot_name_from_identifier = identifier.replace(" ", "_")

    # First, check if the identifier is a valid slot name
    if slot_name_from_identifier in player.equipment:
        success, message = player.unequip_item(slot_name_from_identifier)
        return f"{FORMAT_SUCCESS}{message}{FORMAT_RESET}" if success else f"{FORMAT_ERROR}{message}{FORMAT_RESET}"

    # If not a slot, treat it as an item name and search equipped items
    exact_matches, partial_matches = [], []
    for slot, item in player.equipment.items():
        if item:
            if identifier == item.name.lower():
                exact_matches.append(slot)
            elif identifier in item.name.lower():
                partial_matches.append(slot)

    matches = exact_matches or partial_matches
    
    if not matches:
        return f"{FORMAT_ERROR}You don't have an item called '{identifier}' equipped.{FORMAT_RESET}"
    elif len(matches) > 1:
        ambiguous_items = [f"{player.equipment[s].name} ({s})" for s in matches]
        return f"{FORMAT_ERROR}You have multiple items like that equipped. Please specify which to unequip: {', '.join(ambiguous_items)}{FORMAT_RESET}"
    else:
        slot_to_unequip = matches[0]
        success, message = player.unequip_item(slot_to_unequip)
        return f"{FORMAT_SUCCESS}{message}{FORMAT_RESET}" if success else f"{FORMAT_ERROR}{message}{FORMAT_RESET}"
