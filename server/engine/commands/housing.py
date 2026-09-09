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
