from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET


@command("embark", ["ride"], "movement",
         "Climb aboard a vehicle that is waiting here.\nUsage: embark [name]   (leave it again with: disembark)")
def board_handler(args, context):
    player = context.get("player")
    world = context.get("world") or getattr(player, "world", None)
    if player is None or world is None:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    riding = world.vehicles.aboard(player)
    if riding:
        return "You are already aboard %s." % world.vehicles.name_of(riding)
    here = world.vehicles.parked_in(player.current_region_id, player.current_room_id)
    if not here:
        return "There is nothing here to board."
    wanted = " ".join(args).strip().lower()
    if wanted:
        here = [vehicle_id for vehicle_id in here if wanted in (vehicle_id.lower(), world.vehicles.name_of(vehicle_id).lower())
                or wanted in world.vehicles.name_of(vehicle_id).lower()]
        if not here:
            return "There is nothing like '%s' here to board." % " ".join(args)
    return world.vehicles.board(player, here[0])


@command("disembark", ["land", "alight"], "movement",
         "Climb down from the vehicle you are riding, leaving it parked here (if it can be set down here).\nUsage: disembark")
def disembark_handler(args, context):
    player = context.get("player")
    world = context.get("world") or getattr(player, "world", None)
    if player is None or world is None:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    return world.vehicles.disembark(player)
