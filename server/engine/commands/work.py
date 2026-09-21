# engine/commands/work.py
"""Work that takes time: the verbs a player uses on a `work` declaration.

The engine half is `engine/contracts/work.py` — `start`, `collect`, and the two
numbers a job is made of. This module is the surface: what a player can type, in
words that belong to playing rather than to the contract.

Three commands, and the surface question the design doc left open ("how does a
player discover the mechanic at all, in a text game?") is answered the same way
crafting answers it:

* `jobs` lists what can be started *here* — the station in the room decides — and
  what is already running, with how long is left;
* `begin <job>` spends the materials and starts the clock;
* `collect [job]` takes what is ready.

Nothing here decides what work *is*. A label, a duration, a station name and a
yield all come from the declaration; the messages name items by whatever the
content set calls them.
"""
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, FORMAT_TITLE
from engine.contracts import work as work_contract

# Work is presented with the crafting system: same station vocabulary, same
# materials, same capability. A set that wants timed work without crafting needs
# its own capability, which is a manifest change rather than a guess made here.
WORK_CAPABILITY = "crafting"


@command("jobs", ["worklist"], WORK_CAPABILITY,
         "What can be made here, and what is already under way.\nUsage: jobs",
         content_capability=WORK_CAPABILITY)
def jobs_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if player is None:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    declared = work_contract.declared_work(world)
    if not declared:
        return f"{FORMAT_HIGHLIGHT}Nothing here takes time.{FORMAT_RESET}"

    stations = _available_stations(world, player)
    out = [f"{FORMAT_TITLE}WORK{FORMAT_RESET}"]
    if stations:
        out.append("Stations here: %s%s%s" % (
            FORMAT_HIGHLIGHT,
            ", ".join(sorted(station.replace("_", " ").title() for station in stations)),
            FORMAT_RESET,
        ))
    else:
        out.append("Stations here: none")

    out.append("-" * 20)
    for declaration in declared:
        out.append(_describe_declaration(world, declaration, stations))

    running = work_contract.carried_jobs(player) or []
    if running:
        out.append("")
        out.append(f"{FORMAT_TITLE}Under way{FORMAT_RESET}")
        for timer in running:
            seen = work_contract.observe(world, timer)
            if not seen.get("ok"):
                out.append("  (a job this world no longer declares)")
                continue
            state = "ready to collect" if seen["ready"] else "%s left" % _left(seen)
            out.append("  %s%s%s -- %s" % (FORMAT_HIGHLIGHT, seen["label"], FORMAT_RESET, state))
    return "\n".join(out)


@command("begin", ["startjob"], WORK_CAPABILITY,
         "Start a job that takes time.\nUsage: begin <job>",
         content_capability=WORK_CAPABILITY)
def begin_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if player is None:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args:
        return f"{FORMAT_ERROR}Begin what? (Use 'jobs' to see what takes time){FORMAT_RESET}"

    declaration = _resolve(world, args)
    if declaration is None:
        return f"{FORMAT_ERROR}Nothing here is called '{' '.join(args)}'.{FORMAT_RESET}"

    result = work_contract.start(
        world, player, str(declaration.get("id", "")), _available_stations(world, player)
    )
    if not result.get("ok", False):
        return f"{FORMAT_ERROR}{result.get('message', 'That cannot be started.')}{FORMAT_RESET}"
    return f"{FORMAT_SUCCESS}{result.get('message', '')}{FORMAT_RESET}"


@command("collect", ["finishjob"], WORK_CAPABILITY,
         "Take what a job produced.\nUsage: collect [job]",
         content_capability=WORK_CAPABILITY)
def collect_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if player is None:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"

    running = work_contract.carried_jobs(player) or []
    if not running:
        return f"{FORMAT_HIGHLIGHT}You have nothing under way.{FORMAT_RESET}"

    if args:
        wanted = " ".join(str(argument) for argument in args).lower()
        chosen = [
            timer for timer in running
            if _matches(world, timer, wanted)
        ]
        if not chosen:
            return f"{FORMAT_ERROR}No job of yours is called '{wanted}'.{FORMAT_RESET}"
        targets = chosen
    else:
        targets = work_contract.due_jobs(world, player)
        if not targets:
            # Nothing ready is an answer, not a failure: say how long is left so
            # the player knows whether to wait or go and do something else.
            pending = [work_contract.observe(world, timer) for timer in running]
            lines = [
                "  %s: %s left" % (seen.get("label", "a job"), _left(seen))
                for seen in pending if seen.get("ok")
            ]
            return "%sNothing is ready yet.%s\n%s" % (
                FORMAT_HIGHLIGHT, FORMAT_RESET, "\n".join(lines)
            )

    messages = []
    for timer in list(targets):
        result = work_contract.collect(world, player, timer)
        if not result.get("ok", False):
            messages.append(f"{FORMAT_ERROR}{result.get('message', '')}{FORMAT_RESET}")
            continue
        messages.append(f"{FORMAT_SUCCESS}{result.get('message', '')}{FORMAT_RESET}")
    return "\n".join(messages)


# --- reading the room ---------------------------------------------------------

def _available_stations(world, player) -> set:
    """The station types within reach, as the crafting system already answers it.

    Asked rather than reimplemented: a station is an item property, and the
    crafting manager is the one place that knows which items count.
    """
    manager = getattr(getattr(world, "game", None), "crafting_manager", None)
    if manager is None:
        return set()
    try:
        return {str(station).strip() for station in manager.get_nearby_stations(player)}
    except Exception:  # noqa: BLE001 - a room with no items has no stations
        return set()


def _resolve(world, args):
    """The declaration the typed phrase names, by id, label or alias-of-label."""
    from engine.naming import resolve_all

    query = " ".join(str(argument) for argument in args).strip().lower()
    declared = work_contract.declared_work(world)
    if not declared:
        return None
    for declaration in declared:
        if str(declaration.get("id", "")).lower() == query:
            return declaration
    matches = resolve_all(
        query,
        declared,
        name_of=lambda declaration: str(declaration.get("label", "")),
        id_of=lambda declaration: str(declaration.get("id", "")),
    )
    if not matches:
        return None
    if len(matches) > 1 and matches[1].score >= matches[0].score:
        return None
    return matches[0].obj


def _matches(world, timer, query: str) -> bool:
    if not isinstance(timer, dict):
        return False
    work_id = str(timer.get("work", ""))
    if work_id.lower() == query or str(timer.get("id", "")).lower() == query:
        return True
    declaration = work_contract.work_for(world, work_id) or {}
    return str(declaration.get("label", "")).lower() == query


def _describe_declaration(world, declaration, stations) -> str:
    work_id = str(declaration.get("id", ""))
    label = str(declaration.get("label", work_id))
    station = str(declaration.get("station", "") or "").strip()
    needs = ""
    if station and station not in stations:
        needs = "  (needs a %s)" % station.replace("_", " ").title()
    days = declaration.get("duration_days", 0)
    takes = ""
    if isinstance(days, (int, float)) and not isinstance(days, bool) and days > 0:
        takes = "  %s" % _days(float(days))
    yield_note = ", ".join(
        "%d x %s" % (
            int(entry.get("quantity", 1)),
            work_contract.item_label(world, str(entry.get("item_id", ""))),
        )
        for entry in declaration.get("outputs", [])
        if isinstance(entry, dict)
    )
    line = "  %s%s%s%s%s" % (FORMAT_HIGHLIGHT, label, FORMAT_RESET, takes, needs)
    return line + ("  -> %s" % yield_note if yield_note else "")


def _left(seen) -> str:
    remaining = seen.get("remaining_days")
    if not isinstance(remaining, (int, float)):
        return "an unknown time"
    if remaining >= 1.0:
        return "%.1f days" % remaining
    hours = max(0.0, float(remaining)) * 24.0
    if hours >= 1.0:
        return "%.0f hours" % hours
    return "under an hour"


def _days(days: float) -> str:
    if days >= 1.0:
        return "%.1f days" % days
    return "%.0f hours" % (days * 24.0)
