# engine/commands/interaction/traps.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS, TRAP_DISARM_TRIGGER_MARGIN_THRESHOLD
from engine.core.skill_system import SkillSystem
from engine.items.container import Container
from engine.items.lockpick import Lockpick


@command("disarm", [], "interaction",
         "Attempt to disarm a trap on a container using a lockpick -- "
         "reuses your lockpicking skill. A narrow miss fails safely and "
         "can be retried; a bad one can set the trap off.\n"
         "Usage: disarm <item_name>")
def disarm_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Disarm what? Usage: disarm <item_name>{FORMAT_RESET}"

    name = " ".join(args).lower()
    target = world.find_item_in_room_for_player(name, player)
    if not target: target = player.inventory.find_item_by_name(name)
    if not isinstance(target, Container):
        return f"{FORMAT_ERROR}You don't see a container called '{name}'.{FORMAT_RESET}"

    if not target.properties.get("trapped"):
        return f"You look the {target.name} over carefully, but find nothing to disarm."

    lockpick_item = None
    for slot in player.inventory.slots:
        if isinstance(slot.item, Lockpick):
            lockpick_item = slot.item
            break
    if not lockpick_item:
        return f"{FORMAT_ERROR}You need a lockpick to disarm anything.{FORMAT_RESET}"

    difficulty = int(target.get_property("trap_difficulty", 20) or 20)
    success, _, margin = SkillSystem.attempt_check_with_margin(player, "lockpicking", difficulty)

    if success:
        target.properties["trapped"] = False
        xp_msg = SkillSystem.grant_xp(player, "lockpicking", max(10, difficulty // 2))
        return f"{FORMAT_SUCCESS}You carefully disarm the trap on the {target.name}.{FORMAT_RESET}{xp_msg}"

    wear_msg = lockpick_item.apply_wear(player, margin) or ""
    xp_msg = SkillSystem.grant_xp(player, "lockpicking", 2)
    if abs(margin) >= TRAP_DISARM_TRIGGER_MARGIN_THRESHOLD:
        trap_msg = target.trigger_trap(player) or ""
        return f"{FORMAT_ERROR}Your hand slips!{FORMAT_RESET}{trap_msg}{wear_msg}{xp_msg}"
    return f"{FORMAT_ERROR}You fumble with the mechanism but don't set anything off.{FORMAT_RESET}{wear_msg}{xp_msg}"
