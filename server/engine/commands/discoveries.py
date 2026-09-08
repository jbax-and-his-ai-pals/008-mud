from engine.commands.command_system import command


@command("discoveries", ["discovery", "catalogue", "catalog"], "information", "Review unlocked discoveries.", content_capability="discoveries")
def discoveries_handler(args, context):
    player = context.get("player")
    manager = getattr(context.get("game"), "discovery_manager", None)
    if player is None or manager is None:
        return "Discovery journal unavailable."
    return manager.status(player)
