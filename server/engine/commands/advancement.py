# engine/commands/advancement.py
"""Commands for the P4 progression spine.

Three surfaces, one idea: a player should be able to see what they have done,
what it earned them, and who they have become.

  * `advancement` -- the field journal: everywhere you have been and everything
    you have found. This is the visible half of the activity ledger, and it is
    what makes exploration pay on its own.
  * `title` -- wear a title you have earned, or take one off.
  * `backgrounds` / `background` -- the starting choice, and a reminder of the
    one you made.

Naming note: `journal` is already the quest log (see commands/quest.py), and
`registered_commands` is a flat name->handler map, so claiming that word here
would silently shadow the quest log. The field journal is therefore
`advancement`, with `fieldjournal` as its alias.
"""

from engine.commands.command_system import command
from engine.config import (
    FORMAT_CATEGORY,
    FORMAT_ERROR,
    FORMAT_HIGHLIGHT,
    FORMAT_RESET,
    FORMAT_SUCCESS,
    FORMAT_TITLE,
)


def _advancement(context):
    world = context.get("world")
    if world is None:
        return None
    manager = getattr(world, "advancement_manager", None)
    if manager is not None:
        return manager
    # Fall back through the server, for a world built before wiring.
    server = getattr(world, "server", None)
    return getattr(server, "advancement_manager", None) if server is not None else None


def _titles(context):
    world = context.get("world")
    if world is None:
        return None
    manager = getattr(world, "title_manager", None)
    if manager is not None:
        return manager
    server = getattr(world, "server", None)
    return getattr(server, "title_manager", None) if server is not None else None


def _backgrounds(context):
    world = context.get("world")
    if world is None:
        return None
    server = getattr(world, "server", None)
    return getattr(server, "background_manager", None) if server is not None else None


@command(
    "advancement",
    ["fieldjournal", "progress"],
    "information",
    "Review everywhere you have been and everything you have found.",
)
def advancement_handler(args, context):
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    manager = _advancement(context)
    if manager is None:
        return "Your journal is unavailable."

    text = manager.status(player)
    progression = getattr(getattr(player, "runtime_state", None), "progression", None)
    if progression is not None:
        level_line = "%sLevel %d%s (%d/%d XP)" % (
            FORMAT_CATEGORY, progression.level, FORMAT_RESET,
            progression.experience, progression.experience_to_level,
        )
        text = level_line + "\n\n" + text
    return text


@command(
    "title",
    ["mytitle", "wearth"],
    "information",
    "Review the titles you have earned, or wear one.\nUsage: title [<name> | none]",
)
def title_handler(args, context):
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    manager = _titles(context)
    if manager is None:
        return "Titles are unavailable in this world."

    if not args:
        # Reading the list also refreshes entitlement, so a player who just met
        # a condition sees it immediately rather than after some later event.
        manager.sync(player)
        return manager.status(player)

    wanted = " ".join(str(a) for a in args).strip()
    result = manager.set_active(player, wanted)
    if result.startswith(FORMAT_ERROR):
        return result
    return "%s%s%s" % (FORMAT_SUCCESS, result, FORMAT_RESET)


@command(
    "backgrounds",
    ["bglist"],
    "information",
    "Review the backgrounds available at character creation.",
)
def backgrounds_handler(args, context):
    manager = _backgrounds(context)
    if manager is None:
        return "Backgrounds are unavailable in this world."
    return manager.listing()


@command(
    "background",
    ["mybackground"],
    "information",
    "Review the background your character began with.",
)
def background_handler(args, context):
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    manager = _backgrounds(context)
    if manager is None:
        return "Backgrounds are unavailable in this world."
    return manager.status(player)
