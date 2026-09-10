# engine/commands/jail.py
import random
import time
from engine.commands.command_system import command
from engine.config import (
    FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET,
    JAIL_SEARCH_SUCCESS_CHANCE, JAIL_SEARCH_REWARD_GOLD_MIN, JAIL_SEARCH_REWARD_GOLD_MAX,
)


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

    remaining = player.jailed_until - time.time()
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

    room = world.get_current_room(player)
    if not room or not room.properties.get("is_jail_cell"):
        return f"{FORMAT_ERROR}There's nothing to search here.{FORMAT_RESET}"

    if random.random() < JAIL_SEARCH_SUCCESS_CHANCE:
        gold = random.randint(JAIL_SEARCH_REWARD_GOLD_MIN, JAIL_SEARCH_REWARD_GOLD_MAX)
        player.runtime_state.gold += gold
        return f"{FORMAT_SUCCESS}Digging through the straw, you find {gold} {world.currency_name()} someone missed.{FORMAT_RESET}"

    return "You search the cell but find nothing of use."
