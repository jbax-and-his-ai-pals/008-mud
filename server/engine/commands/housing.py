# engine/commands/housing.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS


@command("buy house", ["buyhouse"], "interaction",
         "Buy a house from a property agent standing nearby.\nUsage: buy house",
         ruleset_system="economy")
def buy_house_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    agent = next(
        (npc for npc in world.get_npcs_for_player(player) if npc.properties.get("sells_houses")),
        None,
    )
    if not agent:
        return f"{FORMAT_ERROR}There is no one here who sells houses.{FORMAT_RESET}"

    success, message = world.housing_manager.buy_house(player, agent)
    color = FORMAT_SUCCESS if success else FORMAT_ERROR
    return f"{color}{message}{FORMAT_RESET}"


@command("expand house", ["expandhouse"], "interaction",
         "Expand your house with a contractor standing nearby.\n"
         "Usage: expand house [branch]",
         ruleset_system="economy")
def expand_house_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    contractor = next(
        (npc for npc in world.get_npcs_for_player(player) if npc.properties.get("can_expand_houses")),
        None,
    )
    if not contractor:
        return f"{FORMAT_ERROR}There is no one here who can expand your house.{FORMAT_RESET}"

    branch = " ".join(args) if args else ""
    success, message = world.housing_manager.expand_house(player, contractor, branch)
    color = FORMAT_SUCCESS if success else FORMAT_ERROR
    return f"{color}{message}{FORMAT_RESET}"


@command("house", [], "interaction",
         "Show your house's current tier and any upgrades a nearby contractor offers.\n"
         "Usage: house")
def house_status_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    contractor = next(
        (npc for npc in world.get_npcs_for_player(player) if npc.properties.get("can_expand_houses")),
        None,
    )
    return world.housing_manager.describe_house_status(player, contractor)
