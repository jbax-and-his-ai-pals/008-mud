# engine/commands/locksmithing.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.items.container import Container


@command("unlock", [], "interaction",
         "Pay a locksmith to open a locked container you're carrying, "
         "bypassing lockpicking entirely.\nUsage: unlock <item_name>",
         ruleset_system="economy")
def unlock_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args:
        return f"{FORMAT_ERROR}What do you want unlocked? Usage: unlock <item_name>{FORMAT_RESET}"

    locksmith = next(
        (npc for npc in world.get_npcs_for_player(player) if npc.properties.get("can_unlock_chests")),
        None,
    )
    if not locksmith:
        return f"{FORMAT_ERROR}There is no one here who can open locks for you.{FORMAT_RESET}"

    item_name = " ".join(args).lower()
    target = player.inventory.find_item_by_name(item_name)
    if not isinstance(target, Container):
        return f"{FORMAT_ERROR}You don't have a container called '{item_name}'.{FORMAT_RESET}"
    if not target.properties.get("locked", False):
        return f"{FORMAT_ERROR}The {target.name} isn't locked.{FORMAT_RESET}"

    difficulty = int(target.get_property("lock_difficulty", 10))
    # Placeholder formula -- exact tuning is a deliberately deferred design
    # question (see docs/design/place_making_and_town_security.md).
    fee = max(5, int(difficulty * 3 + target.weight * 2))

    if player.runtime_state.gold < fee:
        return (
            f"{FORMAT_ERROR}{locksmith.name} wants {fee} {world.currency_name()} to open the {target.name}, "
            f"but you only have {player.runtime_state.gold}.{FORMAT_RESET}"
        )

    player.runtime_state.gold -= fee
    target.properties["locked"] = False

    was_trapped = bool(target.properties.get("trapped"))
    if was_trapped:
        # A locksmith safely defuses any trap as part of the job -- no
        # roll, no damage. Real extra value for the fee over DIY picking.
        target.properties["trapped"] = False
    trap_note = f" {locksmith.name} also carefully disarms a hidden trap along the way." if was_trapped else ""

    return (
        f"{FORMAT_SUCCESS}You pay {fee} {world.currency_name()}. {locksmith.name} makes quick work of the "
        f"{target.name}'s lock.{trap_note}{FORMAT_RESET}\nYour {world.currency_name().capitalize()}: {player.runtime_state.gold}"
    )
