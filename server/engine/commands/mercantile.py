# engine/commands/mercantile.py
from typing import Any, Dict, List, Tuple, Optional
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE, 
    VENDOR_LIST_ITEM_NAME_WIDTH, VENDOR_LIST_PRICE_WIDTH, 
    DEFAULT_VENDOR_BUY_MULTIPLIER, DEFAULT_VENDOR_SELL_MULTIPLIER, 
    REPAIR_COST_PER_VALUE_POINT, REPAIR_MINIMUM_COST, 
    VENDOR_CAN_BUY_ALL_ITEMS, VENDOR_MIN_BUY_PRICE, VENDOR_MIN_SELL_PRICE
)
from engine.items.item_factory import ItemFactory
from engine.items.item import Item
from engine.player import Player
from engine.npcs.npc import NPC


def _grant_party_sale_gold(world, player: Player, total_gold_gain: int) -> str:
    server = getattr(world, "server", None)
    if server is not None and hasattr(server, "grant_party_gold"):
        return str(server.grant_party_gold(player, total_gold_gain))
    player.runtime_state.gold += total_gold_gain
    return ""

def _get_price_multiplier(vendor: NPC) -> float:
    base = DEFAULT_VENDOR_SELL_MULTIPLIER
    if "economy_impact" in vendor.properties:
        discount = vendor.properties["economy_impact"].get("discount", 0.0)
        return max(0.1, base - discount)
    return base

def _display_vendor_inventory(player: Player, vendor: NPC, world) -> str:
    vendor_items_refs = vendor.properties.get("sells_items", [])
    
    display_lines = [f"{FORMAT_TITLE}{vendor.name}'s Wares:{FORMAT_RESET}\n"]
    
    current_multiplier = _get_price_multiplier(vendor)
    if current_multiplier < DEFAULT_VENDOR_SELL_MULTIPLIER:
        display_lines.append(f"{FORMAT_HIGHLIGHT}(Special Discount Active!){FORMAT_RESET}\n")

    if vendor_items_refs:
        for item_ref in vendor_items_refs:
            item_id = item_ref.get("item_id")
            if not item_id: continue
            
            template = world.item_templates.get(item_id)
            if not template: continue
                
            item_name = template.get("name", "Unknown Item")
            base_value = template.get("value", 0)
            
            # Combine item-specific multiplier with vendor global multiplier (discount)
            # Item specific multiplier is usually 1.0 or higher.
            # Vendor global multiplier starts at 2.0 (DEFAULT_SELL) and lowers with discount.
            # Effective Price = Base * ItemMult * (VendorMult / DefaultVendorMult) ??
            # Or simpler: The stored price_multiplier in item_ref IS the sell price factor relative to base value.
            # Default is 2.0. If item has 5.0, it's expensive.
            # If we apply a discount (e.g. 0.2 off), we should reduce the final factor.
            
            item_mult = item_ref.get("price_multiplier", DEFAULT_VENDOR_SELL_MULTIPLIER)
            
            # Calculate discount ratio
            discount_ratio = current_multiplier / DEFAULT_VENDOR_SELL_MULTIPLIER
            final_mult = item_mult * discount_ratio
            
            buy_price = max(VENDOR_MIN_BUY_PRICE, int(base_value * final_mult))
            
            display_lines.append(f"- {item_name:<{VENDOR_LIST_ITEM_NAME_WIDTH}} | Price: {buy_price:>{VENDOR_LIST_PRICE_WIDTH}} gold")

    for slot in vendor.inventory.slots:
        if slot.item:
            item_name = slot.item.name
            
            # Dynamic stock usually uses default multiplier
            buy_price = max(VENDOR_MIN_BUY_PRICE, int(slot.item.value * current_multiplier))
            
            qty_str = f" (x{slot.quantity})" if slot.quantity > 1 else ""
            display_lines.append(f"- {item_name}{qty_str:<{VENDOR_LIST_ITEM_NAME_WIDTH - len(qty_str)}} | Price: {buy_price:>{VENDOR_LIST_PRICE_WIDTH}} gold")

    if len(display_lines) == 1:
        return f"{vendor.name} has nothing to sell right now."

    display_lines.append(f"\nYour Gold: {player.runtime_state.gold}\n\nCommands: list, buy <item> [qty], sell <item> [qty], stoptrade")
    return "\n".join(display_lines)

def _calculate_repair_cost(item: Item) -> Tuple[Optional[int], Optional[str]]:
    current_durability = item.get_property("durability")
    max_durability = item.get_property("max_durability")
    if current_durability is None or max_durability is None: return None, f"The {item.name} doesn't have durability."
    if current_durability >= max_durability: return 0, None
    repair_cost = max(REPAIR_MINIMUM_COST, int(item.value * REPAIR_COST_PER_VALUE_POINT))
    return repair_cost, None

@command("trade", ["shop"], "interaction", "Initiate trade with a vendor.\nUsage: trade <npc_name>", ruleset_system="economy")
def trade_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You cannot trade while dead.{FORMAT_RESET}"
    if player.trading_with:
        old_vendor = world.get_npc(player.trading_with)
        if old_vendor: old_vendor.is_trading = False
        player.trading_with = None
    if not args: return f"{FORMAT_ERROR}Trade with whom?{FORMAT_RESET}"
    npc_name = " ".join(args).lower()
    vendor = world.find_npc_in_room_for_player(npc_name, player)
    if not vendor: return f"{FORMAT_ERROR}You don't see '{npc_name}' here.{FORMAT_RESET}"
    if not vendor.properties.get("is_vendor", False): return f"{FORMAT_ERROR}{vendor.name} doesn't seem interested in trading.{FORMAT_RESET}"
    vendor.is_trading = True
    player.trading_with = vendor.obj_id
    greeting = vendor.dialog.get("trade", vendor.dialog.get("greeting", "What can I do for you?")).format(name=vendor.name)
    response = f"You approach {vendor.name} to trade.\n{FORMAT_HIGHLIGHT}\"{greeting}\"{FORMAT_RESET}\n\n"
    response += _display_vendor_inventory(player, vendor, world)
    return response

@command("list", ["browse"], "interaction", "List items available from the current vendor.\nUsage: list", ruleset_system="economy")
def list_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.trading_with: return f"{FORMAT_ERROR}You are not currently trading with anyone.{FORMAT_RESET}"
    
    vendor = world.get_npc(player.trading_with)
    if not vendor or vendor.current_region_id != player.current_region_id or vendor.current_room_id != player.current_room_id:
        player.trading_with = None
        return f"{FORMAT_ERROR}The vendor you were trading with is no longer here.{FORMAT_RESET}"
        
    return _display_vendor_inventory(player, vendor, world)

@command("buy", [], "interaction", "Buy an item from the current vendor.\nUsage: buy <item_name> [quantity]", ruleset_system="economy")
def buy_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.trading_with: return f"{FORMAT_ERROR}You need to 'trade' with someone first.{FORMAT_RESET}"
    
    vendor = world.get_npc(player.trading_with)
    if not vendor or vendor.current_region_id != player.current_region_id or vendor.current_room_id != player.current_room_id:
        player.trading_with = None
        return f"{FORMAT_ERROR}The vendor you were trading with is gone.{FORMAT_RESET}"
        
    if not args: return f"{FORMAT_ERROR}Buy what? Usage: buy <item_name> [quantity]{FORMAT_RESET}"

    item_name = ""; quantity = 1
    try:
        if args[-1].isdigit():
            quantity = int(args[-1])
            if quantity <= 0: return f"{FORMAT_ERROR}Quantity must be positive.{FORMAT_RESET}"
            item_name = " ".join(args[:-1]).lower()
        else: item_name = " ".join(args).lower()
    except ValueError: return f"{FORMAT_ERROR}Invalid quantity specified.{FORMAT_RESET}"
    if not item_name: return f"{FORMAT_ERROR}You must specify an item name.{FORMAT_RESET}"

    # Calculate current effective multiplier (including discounts)
    current_multiplier = _get_price_multiplier(vendor)
    discount_ratio = current_multiplier / DEFAULT_VENDOR_SELL_MULTIPLIER

    found_inv_item = vendor.inventory.find_item_by_name(item_name)
    
    if found_inv_item:
        available_qty = vendor.inventory.count_item(found_inv_item.obj_id)
        if quantity > available_qty:
            return f"{FORMAT_ERROR}{vendor.name} only has {available_qty} {found_inv_item.name}(s).{FORMAT_RESET}"
            
        base_value = found_inv_item.value
        buy_price_per_item = max(VENDOR_MIN_BUY_PRICE, int(base_value * current_multiplier))
        total_cost = buy_price_per_item * quantity
        
        if player.runtime_state.gold < total_cost: return f"{FORMAT_ERROR}You don't have enough gold (Need {total_cost}, have {player.runtime_state.gold}).{FORMAT_RESET}"

        can_add, inv_msg = player.inventory.can_add_item(found_inv_item, quantity)
        if not can_add: return f"{FORMAT_ERROR}{inv_msg}{FORMAT_RESET}"
        
        player.runtime_state.gold -= total_cost
        
        removed_item, removed_qty, _ = vendor.inventory.remove_item(found_inv_item.obj_id, quantity)
        
        if removed_item:
            if removed_item.stackable and removed_item.obj_id in world.item_templates:
                for _ in range(quantity):
                    new_item = ItemFactory.create_item_from_template(removed_item.obj_id, world)
                    if new_item: player.inventory.add_item(new_item)
            else:
                player.inventory.add_item(removed_item, quantity)

        return f"{FORMAT_SUCCESS}You buy {quantity} {found_inv_item.name}{'' if quantity == 1 else 's'} for {total_cost} gold.{FORMAT_RESET}"

    found_item_ref = None; found_template = None
    for item_ref in vendor.properties.get("sells_items", []):
        item_id = item_ref.get("item_id")
        if not item_id: continue
        template = world.item_templates.get(item_id)
        if template:
            name_in_template = template.get("name", "").lower()
            if item_name == item_id.lower() or item_name == name_in_template:
                found_item_ref = item_ref; found_template = template; break
            elif item_name in name_in_template:
                 found_item_ref = item_ref; found_template = template
                 
    if not found_item_ref or not found_template:
        return f"{FORMAT_ERROR}{vendor.name} doesn't sell '{item_name}'. Type 'list' to see wares.{FORMAT_RESET}"

    item_id = found_template["obj_id"] = found_item_ref["item_id"]
    base_value = found_template.get("value", 0)
    
    item_specific_mult = found_item_ref.get("price_multiplier", DEFAULT_VENDOR_SELL_MULTIPLIER)
    final_mult = item_specific_mult * discount_ratio
    
    buy_price_per_item = max(VENDOR_MIN_BUY_PRICE, int(base_value * final_mult))
    total_cost = buy_price_per_item * quantity
    
    if player.runtime_state.gold < total_cost: return f"{FORMAT_ERROR}You don't have enough gold (Need {total_cost}, have {player.runtime_state.gold}).{FORMAT_RESET}"
    
    temp_item = ItemFactory.create_item_from_template(item_id, world)
    if not temp_item: return f"{FORMAT_ERROR}Internal error creating item '{item_id}'. Cannot buy.{FORMAT_RESET}"
    
    can_add, inv_msg = player.inventory.can_add_item(temp_item, quantity)
    if not can_add: return f"{FORMAT_ERROR}{inv_msg}{FORMAT_RESET}"

    player.runtime_state.gold -= total_cost
    items_added_successfully = 0
    
    for _ in range(quantity):
         item_instance = ItemFactory.create_item_from_template(item_id, world)
         if item_instance:
              added, add_msg = player.inventory.add_item(item_instance, 1)
              if added: items_added_successfully += 1
              else:
                   player.runtime_state.gold += buy_price_per_item * (quantity - items_added_successfully)
                   return f"{FORMAT_ERROR}Failed to add all items to inventory. Transaction partially reverted.{FORMAT_RESET}"
         else:
              player.runtime_state.gold += buy_price_per_item * (quantity - items_added_successfully)
              return f"{FORMAT_ERROR}Failed to create item instance during purchase. Transaction cancelled.{FORMAT_RESET}"
              
    item_display_name = found_template.get("name", item_id)
    return f"{FORMAT_SUCCESS}You buy {quantity} {item_display_name}{'' if quantity == 1 else 's'} for {total_cost} gold.{FORMAT_RESET}\nYour Gold: {player.runtime_state.gold}"

@command("sell", [], "interaction", "Sell an item from your inventory to the current vendor.\nUsage: sell <item_name> [quantity]", ruleset_system="economy")
def sell_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.trading_with: return f"{FORMAT_ERROR}You need to 'trade' with someone first.{FORMAT_RESET}"
    
    vendor = world.get_npc(player.trading_with)
    if not vendor or vendor.current_region_id != player.current_region_id or vendor.current_room_id != player.current_room_id:
        player.trading_with = None
        return f"{FORMAT_ERROR}The vendor you were trading with is gone.{FORMAT_RESET}"
        
    if not args: return f"{FORMAT_ERROR}Sell what? Usage: sell <item_name> [quantity]{FORMAT_RESET}"

    item_name = ""; quantity = 1
    try:
        if args[-1].isdigit():
            quantity = int(args[-1])
            if quantity <= 0: return f"{FORMAT_ERROR}Quantity must be positive.{FORMAT_RESET}"
            item_name = " ".join(args[:-1]).lower()
        else: item_name = " ".join(args).lower()
    except ValueError: return f"{FORMAT_ERROR}Invalid quantity specified.{FORMAT_RESET}"
    if not item_name: return f"{FORMAT_ERROR}You must specify an item name.{FORMAT_RESET}"
    
    item_to_sell = player.inventory.find_item_by_name(item_name)
    if not item_to_sell: return f"{FORMAT_ERROR}You don't have '{item_name}' to sell.{FORMAT_RESET}"
    if player.inventory.count_item(item_to_sell.obj_id) < quantity: return f"{FORMAT_ERROR}You only have {player.inventory.count_item(item_to_sell.obj_id)} {item_to_sell.name}(s) to sell.{FORMAT_RESET}"

    can_sell = False
    vendor_buy_types = vendor.properties.get("buys_item_types", [])
    item_type_name = item_to_sell.__class__.__name__
    if VENDOR_CAN_BUY_ALL_ITEMS or item_type_name in vendor_buy_types or ("Item" in vendor_buy_types and item_type_name == "Item"):
        can_sell = True
    if not can_sell: return f"{FORMAT_ERROR}{vendor.name} is not interested in buying {item_to_sell.name}.{FORMAT_RESET}"
    
    sell_price_per_item = max(VENDOR_MIN_SELL_PRICE, int(item_to_sell.value * DEFAULT_VENDOR_BUY_MULTIPLIER))
    total_gold_gain = sell_price_per_item * quantity
    removed_item_type, actual_removed_count, remove_msg = player.inventory.remove_item(item_to_sell.obj_id, quantity)
    
    if not removed_item_type or actual_removed_count != quantity:
         return f"{FORMAT_ERROR}Something went wrong removing {item_to_sell.name} from your inventory. Sale cancelled.{FORMAT_RESET}"
         
    if removed_item_type:
        vendor.inventory.add_item(removed_item_type, actual_removed_count)

    routing = _grant_party_sale_gold(world, player, total_gold_gain)
    response = f"{FORMAT_SUCCESS}You sell {quantity} {removed_item_type.name}{'' if quantity == 1 else 's'} for {total_gold_gain} gold.{FORMAT_RESET}\nYour Gold: {player.runtime_state.gold}"
    if routing:
        response += f"\n{routing}"
    return response

@command("stoptrade", ["stop", "done"], "interaction", "Stop trading with the current vendor.\nUsage: stoptrade", ruleset_system="economy")
def stoptrade_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.trading_with: return "You are not currently trading with anyone."
    vendor = world.get_npc(player.trading_with)
    if vendor: vendor.is_trading = False
    player.trading_with = None
    return f"You stop trading with {vendor.name if vendor else 'the vendor'}."

@command("repair", [], "interaction", "Ask a capable NPC to repair an item.\nUsage: repair <item_name>", ruleset_system="economy")
def repair_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.is_alive: return f"{FORMAT_ERROR}You can't get items repaired while dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}What item do you want to repair? Usage: repair <item_name>{FORMAT_RESET}"
    item_name_to_repair = " ".join(args).lower()
    
    repair_npc = None
    for npc in world.get_npcs_for_player(player):
        if npc.properties.get("can_repair", False): repair_npc = npc; break
    if not repair_npc: return f"{FORMAT_ERROR}There is no one here who can repair items.{FORMAT_RESET}"
    
    item_to_repair = player.inventory.find_item_by_name(item_name_to_repair)
    if not item_to_repair:
        for slot, equipped_item in player.equipment.items():
            if equipped_item and item_name_to_repair in equipped_item.name.lower():
                 if equipped_item.get_property("durability") is not None:
                     item_to_repair = equipped_item; break
                 else: return f"{FORMAT_ERROR}The {equipped_item.name} cannot be repaired.{FORMAT_RESET}"
    if not item_to_repair: return f"{FORMAT_ERROR}You don't have an item called '{item_name_to_repair}' that can be repaired.{FORMAT_RESET}"

    repair_cost, error_msg = _calculate_repair_cost(item_to_repair)
    if error_msg: return f"{FORMAT_ERROR}{error_msg}{FORMAT_RESET}"
    
    if repair_cost is None: 
        return f"{FORMAT_ERROR}Cannot determine repair cost for {item_to_repair.name}.{FORMAT_RESET}"
    
    if repair_cost == 0: return f"Your {item_to_repair.name} is already in perfect condition."
    
    if player.runtime_state.gold < repair_cost: return f"{FORMAT_ERROR}You need {repair_cost} gold to repair the {item_to_repair.name}, but you only have {player.runtime_state.gold}.{FORMAT_RESET}"

    player.runtime_state.gold -= repair_cost
    item_to_repair.update_property("durability", item_to_repair.get_property("max_durability"))
    return f"{FORMAT_SUCCESS}You pay {repair_cost} gold. {repair_npc.name} repairs your {item_to_repair.name} to perfect condition.{FORMAT_RESET}\nYour Gold: {player.runtime_state.gold}"

@command("repaircost", ["checkrepair", "rcost"], "interaction", "Check the cost to repair an item.\nUsage: repaircost <item_name>", ruleset_system="economy")
def repaircost_handler(args, context):
    world = context["world"]; player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}What item do you want to check the repair cost for? Usage: repaircost <item_name>{FORMAT_RESET}"
    item_name_to_check = " ".join(args).lower()
    
    repair_npc = None
    for npc in world.get_npcs_for_player(player):
        if npc.properties.get("can_repair", False): repair_npc = npc; break
    if not repair_npc: return f"{FORMAT_ERROR}There is no one here who can quote a repair price.{FORMAT_RESET}"

    item_to_check = player.inventory.find_item_by_name(item_name_to_check)
    if not item_to_check:
        for slot, equipped_item in player.equipment.items():
            if equipped_item and item_name_to_check in equipped_item.name.lower():
                if equipped_item.get_property("durability") is not None: item_to_check = equipped_item; break
                else: return f"{FORMAT_ERROR}The {equipped_item.name} cannot be repaired.{FORMAT_RESET}"
    if not item_to_check: return f"{FORMAT_ERROR}You don't have an item called '{item_name_to_check}' that can be repaired.{FORMAT_RESET}"
    
    repair_cost, error_msg = _calculate_repair_cost(item_to_check)
    if error_msg: return f"{FORMAT_ERROR}{error_msg}{FORMAT_RESET}"
    
    if repair_cost is None: return f"{FORMAT_ERROR}Cannot determine repair cost for {item_to_check.name}.{FORMAT_RESET}"
    
    if repair_cost == 0: return f"Your {item_to_check.name} does not need repairing."
    
    return f"{repair_npc.name} quotes a price of {FORMAT_HIGHLIGHT}{repair_cost} gold{FORMAT_RESET} to fully repair your {item_to_check.name}."
