# engine/commands/jail.py
import random
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET


@command("wait", ["rest"], "interaction",
         "Pass the time. If you're serving a jail sentence, this checks "
         "whether it's up yet -- the sentence itself passes on the real "
         "clock regardless.\nUsage: wait")
def wait_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    if player.jailed_until is None:
        return "Time passes."

    remaining = player.jailed_until - world.clock.now()
    if remaining > 0:
        return f"You wait in your cell. It'll be a while yet -- about {int(remaining)} more seconds."

    return world.crime_manager.release_from_jail(player)


@command("search", [], "interaction",
         "Search your surroundings. In a jail cell, this can rarely turn "
         "up something useful.\nUsage: search")
def search_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    custody = world.ruleset_section("crime").get("custody", {})
    room_property = str(custody.get("room_property", "")).strip() if isinstance(custody, dict) else ""

    room = world.get_current_room(player)
    if not room or not room_property or not room.properties.get(room_property):
        return f"{FORMAT_ERROR}There's nothing to search here.{FORMAT_RESET}"

    success_chance = custody.get("search_success_chance", 0) if isinstance(custody, dict) else 0
    if random.random() < success_chance:
        gold_min = int(custody.get("search_currency_min", 0))
        gold_max = int(custody.get("search_currency_max", gold_min))
        gold = random.randint(gold_min, max(gold_min, gold_max))
        player.runtime_state.gold += gold
        return f"{FORMAT_SUCCESS}Digging through the straw, you find {gold} {world.currency_name()} someone missed.{FORMAT_RESET}"

    return "You search the cell but find nothing of use."
