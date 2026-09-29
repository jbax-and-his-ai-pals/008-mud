from engine.commands.command_system import command
from engine.npcs import companions


@command("companions", ["companion", "followers"], "information", "See who is travelling with you.")
def companions_handler(args, context):
    player = context.get("player")
    world = context.get("world") or getattr(player, "world", None)
    if player is None or world is None:
        return "Companions are unavailable."
    lines = companions.party_lines(world, player)
    if not lines:
        if not companions.max_companions(world):
            return "No one travels with you, and no one can in this world."
        return "No one travels with you."
    cap = companions.max_companions(world)
    return "Travelling with you (%d of %d):\n%s" % (len(lines), cap, "\n".join("  " + line for line in lines))
