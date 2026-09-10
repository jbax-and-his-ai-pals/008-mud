# engine/commands/interaction/theft.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET
from engine.items.container import Container
from engine.items.item_factory import ItemFactory
from engine.items.chest_loot_generator import ChestLootGenerator


@command("steal", [], "interaction",
         "Take something that isn't yours -- from a vendor's stock or a "
         "container someone else owns. Risky: anyone present might notice.\n"
         "Usage: steal <item> from <target>")
def steal_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"

    args_lower = [a.lower() for a in args]
    if "from" not in args_lower:
        return f"{FORMAT_ERROR}Usage: steal <item> from <target>{FORMAT_RESET}"

    idx = args_lower.index("from")
    item_name = " ".join(args[:idx]).lower()
    target_name = " ".join(args[idx + 1:]).lower()
    if not item_name or not target_name:
        return f"{FORMAT_ERROR}Usage: steal <item> from <target>{FORMAT_RESET}"

    item = None

    npc_target = world.find_npc_in_room_for_player(target_name, player)
    if npc_target:
        for item_ref in npc_target.properties.get("sells_items", []):
            template = world.item_templates.get(item_ref.get("item_id"))
            if template and item_name in str(template.get("name", "")).lower():
                item = ItemFactory.create_item_from_template(item_ref["item_id"], world)
                break

    if item is None:
        container_target = world.find_item_in_room_for_player(target_name, player)
        if isinstance(container_target, Container) and container_target.properties.get("owned_by_npc"):
            ChestLootGenerator.generate_household_loot(world, container_target)
            found = container_target.find_item_by_name(item_name)
            if found and container_target.remove_item(found):
                item = found

    if item is None:
        return f"{FORMAT_ERROR}There's nothing like that to steal from {target_name}.{FORMAT_RESET}"

    can_add, msg = player.inventory.can_add_item(item)
    if not can_add:
        return f"{FORMAT_ERROR}{msg}{FORMAT_RESET}"
    player.inventory.add_item(item)

    witness = world.crime_manager.attempt_witness(player)
    if not witness:
        return f"{FORMAT_SUCCESS}You slip the {item.name} away, unnoticed.{FORMAT_RESET}"

    item_value = max(0, int(item.value))
    outcome = world.crime_manager.resolve_crime(player, item_value)
    return f"{FORMAT_ERROR}{witness.name} catches you red-handed!{FORMAT_RESET}{outcome}"
