# engine/commands/interaction/theft.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET
from engine.items.container import Container
from engine.items.item_factory import ItemFactory
from engine.items.chest_loot_generator import ChestLootGenerator


def taking_is_theft(container) -> bool:
    """Whether the container's contents belong to somebody.

    One question, asked by every verb that can empty a container. `steal` and
    `get` used to disagree about this: `steal` consulted the owner and rolled a
    witness, while `open locker` followed by `get multitool from locker` took the
    same thing with no risk at all, which made the crime system optional for the
    only containers it was written for.
    """
    return bool(isinstance(container, Container) and container.properties.get("owned_by_npc"))


def taking_consequences(world, player, value: int) -> str:
    """What happens when someone sees the player take what is not theirs.

    Empty when nobody saw: a burglary in an empty room is a burglary, not a
    failure. Shared by every verb so the risk does not depend on the phrasing.
    """
    witness = world.crime_manager.attempt_witness(player)
    if not witness:
        return ""
    return (
        f"\n{FORMAT_ERROR}{witness.name} catches you red-handed!{FORMAT_RESET}"
        + world.crime_manager.resolve_crime(player, max(0, int(value)))
    )


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
        if taking_is_theft(container_target):
            # A container someone owns is filled when it is first *opened*
            # (`containers.open_handler`), so a player can name what they are
            # reaching for. This call is the fallback for a container nobody has
            # opened yet, and it is idempotent -- it marks its work done, and an
            # authored inventory is already done -- so the two never double-fill.
            ChestLootGenerator.fill_owned_container(world, container_target)
            found = container_target.find_item_by_name(item_name)
            if found and container_target.remove_item(found):
                item = found

    if item is None:
        return f"{FORMAT_ERROR}There's nothing like that to steal from {target_name}.{FORMAT_RESET}"

    can_add, msg = player.inventory.can_add_item(item)
    if not can_add:
        return f"{FORMAT_ERROR}{msg}{FORMAT_RESET}"
    player.inventory.add_item(item)

    consequences = taking_consequences(world, player, max(0, int(item.value)))
    if not consequences:
        return f"{FORMAT_SUCCESS}You slip the {item.name} away, unnoticed.{FORMAT_RESET}"
    return consequences
