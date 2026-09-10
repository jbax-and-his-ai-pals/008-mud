# engine/commands/mercantile.py
from typing import Any, Dict, List, Tuple, Optional
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE,
    VENDOR_LIST_ITEM_NAME_WIDTH, VENDOR_LIST_PRICE_WIDTH,
    DEFAULT_VENDOR_BUY_MULTIPLIER, DEFAULT_VENDOR_SELL_MULTIPLIER,
    REPAIR_COST_PER_VALUE_POINT, REPAIR_MINIMUM_COST,
    VENDOR_CAN_BUY_ALL_ITEMS, VENDOR_MIN_BUY_PRICE, VENDOR_MIN_SELL_PRICE,
    LOCKED_CONTAINER_SELL_RATE_PER_WEIGHT
)
from engine.items.item_factory import ItemFactory
from engine.items.item import Item
from engine.items.container import Container
from engine.player import Player
from engine.npcs.npc import NPC
from engine.social.relationships import apply_relationship_milestones, relationship_key, relationship_discount


def _grant_party_sale_gold(world, player: Player, total_gold_gain: int) -> str:
    server = getattr(world, "server", None)
    if server is not None and hasattr(server, "grant_party_gold"):
        return str(server.grant_party_gold(player, total_gold_gain))
    player.runtime_state.gold += total_gold_gain
    return ""

def _template_preview_name(template: Dict) -> str:
    """Name for a vendor listing/match target -- procedural templates (e.g.
    the random-spell-scroll's "Scroll of {spell_name}") aren't resolved until
    an actual instance is rolled at purchase time, so format them with a
    generic placeholder rather than showing the raw '{spell_name}' token."""
    raw_name = template.get("name", "Unknown Item")
    if template.get("properties", {}).get("is_procedural"):
        try:
            return raw_name.format(spell_name="a random spell")
        except (KeyError, IndexError):
            return raw_name
    return raw_name

def _get_price_multiplier(vendor: NPC, player: Optional[Player] = None) -> float:
    base = DEFAULT_VENDOR_SELL_MULTIPLIER
    if "economy_impact" in vendor.properties:
        discount = vendor.properties["economy_impact"].get("discount", 0.0)
        base = max(0.1, base - discount)
    # Personal relationships stack gently with world/economy discounts. This
    # makes friendship valuable without making vendor stock free at high tiers.
    if player is not None:
        bond = int(getattr(player, "npc_relationships", {}).get(relationship_key(vendor), 0))
        base *= 1.0 - relationship_discount(bond, getattr(player, "world", None))
    return max(0.1, base)

def _relationship_requirement(item_ref: Dict[str, Any]) -> int:
    return max(0, min(100, int(item_ref.get("relationship_min", 0))))

def _relationship_allows_stock(player: Player, vendor: NPC, item_ref: Dict[str, Any]) -> bool:
    required = _relationship_requirement(item_ref)
    score = int(getattr(player, "npc_relationships", {}).get(relationship_key(vendor), 0))
    return score >= required

def _display_vendor_inventory(player: Player, vendor: NPC, world) -> str:
    vendor_items_refs = vendor.properties.get("sells_items", [])
    
    display_lines = [f"{FORMAT_TITLE}{vendor.name}'s Wares:{FORMAT_RESET}\n"]
    
    current_multiplier = _get_price_multiplier(vendor, player)
    if current_multiplier < DEFAULT_VENDOR_SELL_MULTIPLIER:
        display_lines.append(f"{FORMAT_HIGHLIGHT}(Special Discount Active!){FORMAT_RESET}\n")

    if vendor_items_refs:
        for item_ref in vendor_items_refs:
            item_id = item_ref.get("item_id")
            if not item_id: continue
            
            template = world.item_templates.get(item_id)
            if not template: continue
                
            item_name = _template_preview_name(template)
            base_value = template.get("value", 0)
            relationship_required = _relationship_requirement(item_ref)
            if not _relationship_allows_stock(player, vendor, item_ref):
                display_lines.append(f"- {item_name:<{VENDOR_LIST_ITEM_NAME_WIDTH}} | [Friendship {relationship_required}/100 required]")
                continue
            
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
            
            display_lines.append(f"- {item_name:<{VENDOR_LIST_ITEM_NAME_WIDTH}} | Price: {buy_price:>{VENDOR_LIST_PRICE_WIDTH}} {world.currency_name()}")

    for slot in vendor.inventory.slots:
        if slot.item:
            item_name = slot.item.name

            # Dynamic stock usually uses default multiplier
            buy_price = max(VENDOR_MIN_BUY_PRICE, int(slot.item.value * current_multiplier))

            qty_str = f" (x{slot.quantity})" if slot.quantity > 1 else ""
            display_lines.append(f"- {item_name}{qty_str:<{VENDOR_LIST_ITEM_NAME_WIDTH - len(qty_str)}} | Price: {buy_price:>{VENDOR_LIST_PRICE_WIDTH}} {world.currency_name()}")

    if len(display_lines) == 1:
        return f"{vendor.name} has nothing to sell right now."

    if vendor.properties.get("buy_orders"):
        display_lines.append("\nBuy orders available: type 'orders'.")
    display_lines.append(f"\nYour {world.currency_name().capitalize()}: {player.runtime_state.gold}\n\nCommands: list, orders, fulfill <order>, buy <item> [qty], sell <item> [qty], stoptrade")
    return "\n".join(display_lines)

def _active_vendor(player: Player, world) -> Optional[NPC]:
    if not player.trading_with:
        return None
    vendor = world.get_npc(player.trading_with)
    if not vendor or vendor.current_region_id != player.current_region_id or vendor.current_room_id != player.current_room_id:
        player.trading_with = None
        return None
    return vendor

def _vendor_orders(vendor: NPC) -> List[Dict[str, Any]]:
    orders = vendor.properties.get("buy_orders", [])
    return [order for order in orders if isinstance(order, dict) and str(order.get("id", "")).strip()]


def _order_material_quality_requirement(order: Dict[str, Any]) -> int:
    value = order.get("min_material_quality_score", 0)
    return max(0, int(value)) if isinstance(value, int) and not isinstance(value, bool) else 0

@command("orders", ["buyorders"], "interaction", "List buy orders from the current vendor.", ruleset_system="economy")
def orders_handler(args, context):
    world = context["world"]; player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    vendor = _active_vendor(player, world)
    if vendor is None:
        return f"{FORMAT_ERROR}You need to 'trade' with someone first.{FORMAT_RESET}"
    completed = set(player.vendor_orders_completed.get(relationship_key(vendor), []))
    lines = [f"{FORMAT_TITLE}{vendor.name}'s Buy Orders:{FORMAT_RESET}"]
    for order in _vendor_orders(vendor):
        order_id = str(order["id"])
        item_id = str(order.get("item_id", ""))
        template = world.item_templates.get(item_id, {})
        item_name = str(template.get("name", item_id or "unknown item"))
        quantity = max(1, int(order.get("quantity", 1)))
        reward = max(0, int(order.get("reward_gold", 0)))
        repeatable = bool(order.get("repeatable", False))
        if order_id in completed and not repeatable:
            state = "complete"
        else:
            state = "repeatable" if repeatable else "available"
        quality_required = _order_material_quality_requirement(order)
        quality_note = f"; material quality {quality_required}+" if quality_required else ""
        lines.append(f"- {order_id}: {quantity} x {item_name} — {reward} {world.currency_name()} ({state}{quality_note})")
    if len(lines) == 1:
        return f"{vendor.name} has no active buy orders."
    lines.append("Use: fulfill <order id>")
    return "\n".join(lines)

@command("fulfill", ["fillorder"], "interaction", "Fulfill a current vendor buy order.\nUsage: fulfill <order id>", ruleset_system="economy")
def fulfill_handler(args, context):
    world = context["world"]; player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    vendor = _active_vendor(player, world)
    if vendor is None:
        return f"{FORMAT_ERROR}You need to 'trade' with someone first.{FORMAT_RESET}"
    order_id = " ".join(args).strip().lower()
    if not order_id:
        return f"{FORMAT_ERROR}Fulfill which order? Type 'orders' to inspect them.{FORMAT_RESET}"
    order = next((entry for entry in _vendor_orders(vendor) if str(entry["id"]).lower() == order_id), None)
    if order is None:
        return f"{FORMAT_ERROR}{vendor.name} has no order named '{order_id}'.{FORMAT_RESET}"
    vendor_key = relationship_key(vendor)
    completed = player.vendor_orders_completed.setdefault(vendor_key, [])
    if str(order["id"]) in completed and not bool(order.get("repeatable", False)):
        return f"{FORMAT_ERROR}You have already completed that order.{FORMAT_RESET}"
    item_id = str(order.get("item_id", ""))
    quantity = max(1, int(order.get("quantity", 1)))
    item = player.inventory.find_item_by_id(item_id)
    if item is None or player.inventory.count_item(item_id) < quantity:
        return f"{FORMAT_ERROR}You need {quantity} x {world.item_templates.get(item_id, {}).get('name', item_id)} for this order.{FORMAT_RESET}"
    if bool(order.get("crafted_only", False)) and not bool(item.get_property("crafted_by_player", False)):
        return f"{FORMAT_ERROR}This order requires an item crafted by you.{FORMAT_RESET}"
    quality_required = _order_material_quality_requirement(order)
    if quality_required:
        qualified_items = [
            slot.item for slot in player.inventory.slots
            if slot.item is not None and slot.item.obj_id == item_id
            and isinstance(slot.item.get_property("material_quality_score", 0), int)
            and not isinstance(slot.item.get_property("material_quality_score", 0), bool)
            and slot.item.get_property("material_quality_score", 0) >= quality_required
            and (not bool(order.get("crafted_only", False)) or bool(slot.item.get_property("crafted_by_player", False)))
        ]
        if len(qualified_items) < quantity:
            return f"{FORMAT_ERROR}This order requires {quantity} item(s) with material quality {quality_required} or better.{FORMAT_RESET}"
        removed_items = []
        for qualified_item in qualified_items[:quantity]:
            if not player.inventory.remove_item_instance(qualified_item):
                return f"{FORMAT_ERROR}The order could not be fulfilled safely.{FORMAT_RESET}"
            removed_items.append(qualified_item)
        removed = removed_items[0]
        count = len(removed_items)
    else:
        removed, count, _message = player.inventory.remove_item(item_id, quantity)
    if removed is None or count != quantity:
        return f"{FORMAT_ERROR}The order could not be fulfilled safely.{FORMAT_RESET}"
    reward = max(0, int(order.get("reward_gold", 0)))
    routing = _grant_party_sale_gold(world, player, reward)
    relationship = int(order.get("relationship_amount", 0))
    if relationship:
        old_score = int(player.npc_relationships.get(vendor_key, 0))
        new_score = max(0, min(100, old_score + relationship))
        player.npc_relationships[vendor_key] = new_score
        milestone_note = apply_relationship_milestones(player, vendor, old_score, new_score, world)
    else:
        milestone_note = ""
    if not bool(order.get("repeatable", False)):
        completed.append(str(order["id"]))
    response = f"{FORMAT_SUCCESS}Order fulfilled: {quantity} x {removed.name} for {reward} {world.currency_name()}.{FORMAT_RESET}"
    if relationship:
        response += f"\nRelationship with {vendor.name}: {'+' if relationship > 0 else ''}{relationship}"
    if milestone_note:
        response += f"\n{milestone_note}"
    if routing:
        response += f"\n{routing}"
    return response

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
    current_multiplier = _get_price_multiplier(vendor, player)
    discount_ratio = current_multiplier / DEFAULT_VENDOR_SELL_MULTIPLIER

    found_inv_item = vendor.inventory.find_item_by_name(item_name)
    
    if found_inv_item:
        available_qty = vendor.inventory.count_item(found_inv_item.obj_id)
        if quantity > available_qty:
            return f"{FORMAT_ERROR}{vendor.name} only has {available_qty} {found_inv_item.name}(s).{FORMAT_RESET}"
            
        base_value = found_inv_item.value
        buy_price_per_item = max(VENDOR_MIN_BUY_PRICE, int(base_value * current_multiplier))
        total_cost = buy_price_per_item * quantity
        
        if player.runtime_state.gold < total_cost: return f"{FORMAT_ERROR}You don't have enough {world.currency_name()} (Need {total_cost}, have {player.runtime_state.gold}).{FORMAT_RESET}"

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

        return f"{FORMAT_SUCCESS}You buy {quantity} {found_inv_item.name}{'' if quantity == 1 else 's'} for {total_cost} {world.currency_name()}.{FORMAT_RESET}"

    found_item_ref = None; found_template = None
    for item_ref in vendor.properties.get("sells_items", []):
        item_id = item_ref.get("item_id")
        if not item_id: continue
        template = world.item_templates.get(item_id)
        if template:
            name_in_template = _template_preview_name(template).lower()
            if item_name == item_id.lower() or item_name == name_in_template:
                found_item_ref = item_ref; found_template = template; break
            elif item_name in name_in_template:
                 found_item_ref = item_ref; found_template = template
                 
    if not found_item_ref or not found_template:
        return f"{FORMAT_ERROR}{vendor.name} doesn't sell '{item_name}'. Type 'list' to see wares.{FORMAT_RESET}"
    if not _relationship_allows_stock(player, vendor, found_item_ref):
        required = _relationship_requirement(found_item_ref)
        current = int(getattr(player, "npc_relationships", {}).get(relationship_key(vendor), 0))
        return f"{FORMAT_ERROR}{vendor.name} reserves that for trusted friends ({current}/{required} relationship).{FORMAT_RESET}"

    item_id = found_template["obj_id"] = found_item_ref["item_id"]
    base_value = found_template.get("value", 0)
    
    item_specific_mult = found_item_ref.get("price_multiplier", DEFAULT_VENDOR_SELL_MULTIPLIER)
    final_mult = item_specific_mult * discount_ratio
    
    buy_price_per_item = max(VENDOR_MIN_BUY_PRICE, int(base_value * final_mult))
    total_cost = buy_price_per_item * quantity
    
    if player.runtime_state.gold < total_cost: return f"{FORMAT_ERROR}You don't have enough {world.currency_name()} (Need {total_cost}, have {player.runtime_state.gold}).{FORMAT_RESET}"

    temp_item = ItemFactory.create_item_from_template(item_id, world)
    if not temp_item: return f"{FORMAT_ERROR}Internal error creating item '{item_id}'. Cannot buy.{FORMAT_RESET}"
    
    can_add, inv_msg = player.inventory.can_add_item(temp_item, quantity)
    if not can_add: return f"{FORMAT_ERROR}{inv_msg}{FORMAT_RESET}"

    player.runtime_state.gold -= total_cost
    items_added_successfully = 0
    last_item_name = _template_preview_name(found_template)

    for _ in range(quantity):
         item_instance = ItemFactory.create_item_from_template(item_id, world)
         if item_instance:
              last_item_name = item_instance.name
              added, add_msg = player.inventory.add_item(item_instance, 1)
              if added: items_added_successfully += 1
              else:
                   player.runtime_state.gold += buy_price_per_item * (quantity - items_added_successfully)
                   return f"{FORMAT_ERROR}Failed to add all items to inventory. Transaction partially reverted.{FORMAT_RESET}"
         else:
              player.runtime_state.gold += buy_price_per_item * (quantity - items_added_successfully)
              return f"{FORMAT_ERROR}Failed to create item instance during purchase. Transaction cancelled.{FORMAT_RESET}"

    item_display_name = last_item_name if quantity == 1 else _template_preview_name(found_template)
    return f"{FORMAT_SUCCESS}You buy {quantity} {item_display_name}{'' if quantity == 1 else 's'} for {total_cost} {world.currency_name()}.{FORMAT_RESET}\nYour {world.currency_name().capitalize()}: {player.runtime_state.gold}"

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

    if item_to_sell.get_property("quest_item"):
        return f"{FORMAT_ERROR}{item_to_sell.name} isn't something you can part with.{FORMAT_RESET}"

    if isinstance(item_to_sell, Container) and item_to_sell.properties.get("locked"):
        # Nobody buying a still-locked container knows what's inside, so
        # its value (and whatever it contains) never factors into the
        # price -- deliberately worse than unlocking it and selling the
        # contents separately.
        sell_price_per_item = max(VENDOR_MIN_SELL_PRICE, int(item_to_sell.weight * LOCKED_CONTAINER_SELL_RATE_PER_WEIGHT))
    else:
        sell_rate = vendor.properties.get("sell_rate_multiplier", DEFAULT_VENDOR_BUY_MULTIPLIER)
        sell_price_per_item = max(VENDOR_MIN_SELL_PRICE, int(item_to_sell.value * sell_rate))
    total_gold_gain = sell_price_per_item * quantity
    removed_item_type, actual_removed_count, remove_msg = player.inventory.remove_item(item_to_sell.obj_id, quantity)
    
    if not removed_item_type or actual_removed_count != quantity:
         return f"{FORMAT_ERROR}Something went wrong removing {item_to_sell.name} from your inventory. Sale cancelled.{FORMAT_RESET}"
         
    if removed_item_type:
        vendor.inventory.add_item(removed_item_type, actual_removed_count)

    routing = _grant_party_sale_gold(world, player, total_gold_gain)
    response = f"{FORMAT_SUCCESS}You sell {quantity} {removed_item_type.name}{'' if quantity == 1 else 's'} for {total_gold_gain} {world.currency_name()}.{FORMAT_RESET}\nYour {world.currency_name().capitalize()}: {player.runtime_state.gold}"
    if routing:
        response += f"\n{routing}"
    return response

# "stop" is intentionally not an alias here -- system.py's general
# "stop current automated action" command already owns that word (and
# loads after this module), so it silently wins over this one.
@command("stoptrade", ["done"], "interaction", "Stop trading with the current vendor.\nUsage: stoptrade", ruleset_system="economy")
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
    
    if player.runtime_state.gold < repair_cost: return f"{FORMAT_ERROR}You need {repair_cost} {world.currency_name()} to repair the {item_to_repair.name}, but you only have {player.runtime_state.gold}.{FORMAT_RESET}"

    player.runtime_state.gold -= repair_cost
    item_to_repair.update_property("durability", item_to_repair.get_property("max_durability"))
    return f"{FORMAT_SUCCESS}You pay {repair_cost} {world.currency_name()}. {repair_npc.name} repairs your {item_to_repair.name} to perfect condition.{FORMAT_RESET}\nYour {world.currency_name().capitalize()}: {player.runtime_state.gold}"

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
    
    return f"{repair_npc.name} quotes a price of {FORMAT_HIGHLIGHT}{repair_cost} {world.currency_name()}{FORMAT_RESET} to fully repair your {item_to_check.name}."
