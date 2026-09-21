# engine/contracts/work.py
"""Work that takes time: what the engine does with a `work` declaration.

The declaration is content's. This module's whole job is the three things the
engine knows how to do with one, and nothing about what any particular work *is*:

* **start it** -- what it consumes, and when it would end;
* **evaluate it on read** -- ready, or how long is left;
* **complete it** -- what it yields.

There is deliberately no tick loop and no timer state here. A timer is two
absolute numbers (`started_at`, `ends_at`) on whatever carries it, so completion
is a comparison rather than an event: nothing has to fire at a moment, and every
observer agrees because they all compute from the same two numbers. That is also
what makes a duration survive a restart -- a saved `ends_at` is still meaningful
after the process has been down, where a saved "seconds remaining" would not be.

**Which owner.** v1 places a timer on the *player*, because the design scoped
duration to the two owners that already round-trip through a save (a player and an
item; a room's properties are not persisted at all). `start` therefore consumes
from the player's inventory, installs the timer on the player's own work state,
and `collect` puts the yield back into the same inventory. Containers, rooms and
stations as timer owners wait on persisting world state, which is Track C's
question and not one this module should answer by assuming it.

**What this module is not.** It knows no station, no skill and no recipe *name*:
a station arrives as a string the caller looked up (`crafting_station_type` on a
nearby item), a skill as a declaration field it rolls through `SkillSystem`, and
the yield as `outputs`. The moment `if work_id == "..."` appears here, the design
has failed.

Anchoring is `world.clock` and not `TimeManager.game_time`: the first is a
`WallClock` on a live server and a `SimulatedClock` the tests can `set()`, while
the second is a frame-delta calendar that stops when the process does. The long
version, including why, is `docs/design/duration-primitive.md`.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from engine.config import TIME_REAL_SECONDS_PER_GAME_DAY
from engine.contracts.registry import ContractRegistry, registry_for

# A timer's four fields, and the only four the engine reads. Content may add its
# own alongside them; these are the ones with meaning here.
TIMER_FIELDS = ("id", "started_at", "ends_at", "work")

# `duration_days` is *game* days, the same unit as `ResourceNode.respawn_days`,
# and a game day is `TIME_REAL_SECONDS_PER_GAME_DAY` of wall clock -- 20 minutes,
# not 24 hours. This started life as a literal 86400, which made an authored
# "one day" take 72 game days to finish: the multiplier and the clock are in
# different units and only the config knows the exchange rate. The test that pins
# it asserts the *meaning* (`test_work_contract`: a one-day job is due after one
# game day of clock advance and not before), because a test written in terms of
# the same constant would have agreed with the bug.
SECONDS_PER_GAME_DAY = float(TIME_REAL_SECONDS_PER_GAME_DAY)


def work_for(world: Any, work_id: str) -> Optional[Dict[str, Any]]:
    """The declaration an id names in `world`'s content set, or None.

    None rather than an exception, and None rather than a guess: an id that names
    nothing is a content bug, and content validation refuses it before the game
    runs. A caller that gets None should say so and stop, not invent a duration.
    """
    registry: Optional[ContractRegistry] = registry_for(world)
    if registry is None:
        return None
    return registry.work_declaration(work_id)


def declared_work(world: Any) -> List[Dict[str, Any]]:
    """Every `work` declaration this content set makes, in the order declared.

    The order is the file's, which is the only ordering content has any control
    over, so a listing reads the way it was authored.
    """
    registry: Optional[ContractRegistry] = registry_for(world)
    if registry is None:
        return []
    return [entry for entry in registry.work.values() if isinstance(entry, dict)]


def item_label(world: Any, item_id: str) -> str:
    """What this content set calls an item, for a sentence a player reads."""
    return _item_name(world, item_id)


def duration_seconds(declaration: Any) -> float:
    """How long a declaration takes, in seconds. Zero when it declares none.

    Zero is "instant", not "unknown": a `work` entry with no `duration_days` is
    work that finishes the moment it starts, which is how a plain recipe and a
    three-day ferment can be the same kind of declaration.
    """
    if not isinstance(declaration, dict):
        return 0.0
    days = declaration.get("duration_days", 0)
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        return 0.0
    return max(0.0, float(days)) * SECONDS_PER_GAME_DAY


def begin(world: Any, work_id: str, timer_id: str = "") -> Optional[Dict[str, Any]]:
    """A new timer for `work_id`, anchored to the world clock. None if undeclared.

    The timer is returned rather than installed: where it belongs -- a room, a
    container, an entity, a player's own properties -- is a decision this module
    has no business making, and a caller that owns the thing can put it there.
    """
    declaration = work_for(world, work_id)
    if declaration is None:
        return None
    now = _now(world)
    if now is None:
        return None
    return {
        "id": timer_id or str(work_id),
        "started_at": now,
        "ends_at": now + duration_seconds(declaration),
        "work": str(work_id),
    }


def remaining_seconds(world: Any, timer: Any) -> Optional[float]:
    """Seconds until `timer` is due; 0.0 when due; None when it is not a timer.

    Never negative: a timer a week overdue is finished, not "-604800 seconds
    left", and every reader that has to clamp that would eventually clamp it
    differently.
    """
    if not isinstance(timer, dict):
        return None
    ends_at = timer.get("ends_at")
    if isinstance(ends_at, bool) or not isinstance(ends_at, (int, float)):
        return None
    now = _now(world)
    if now is None:
        return None
    return max(0.0, float(ends_at) - now)


def is_due(world: Any, timer: Any) -> bool:
    """Whether the world clock has reached `timer`'s end.

    A timer that cannot be read is not due: failing closed keeps an unreadable
    record from silently completing work nobody asked to complete.
    """
    remaining = remaining_seconds(world, timer)
    return remaining is not None and remaining <= 0.0


def observe(world: Any, timer: Any) -> Dict[str, Any]:
    """What a reader needs to say about a timer, without completing it.

    The shape is stable and the label comes from the declaration, so a caller can
    print `status` and be right for work it has never heard of.
    """
    if not isinstance(timer, dict):
        return {"ok": False, "reason": "not a timer"}
    declaration = work_for(world, str(timer.get("work", "")))
    if declaration is None:
        return {"ok": False, "reason": "undeclared work '%s'" % str(timer.get("work", ""))}

    remaining = remaining_seconds(world, timer)
    if remaining is None:
        return {"ok": False, "reason": "timer has no readable end"}

    return {
        "ok": True,
        "work": str(timer.get("work", "")),
        "label": str(declaration.get("label", timer.get("work", ""))),
        "ready": remaining <= 0.0,
        "remaining_seconds": remaining,
        "remaining_days": remaining / SECONDS_PER_GAME_DAY,
        "started_at": timer.get("started_at"),
        "ends_at": timer.get("ends_at"),
    }


def declaration_issues(declaration: Any) -> List[str]:
    """Vocabulary problems in one declaration that the schema cannot see.

    The schema checks types; this checks that a name means something. A work entry
    naming a skill no set declares is the failure this project keeps meeting -- it
    reads as configured and gates nothing -- so it is reported rather than left to
    be discovered as "the check never fails".
    """
    issues: List[str] = []
    if not isinstance(declaration, dict):
        return ["work must be an object"]

    work_id = str(declaration.get("id", "")).strip() or "(unnamed)"
    skill = str(declaration.get("skill", "") or "").strip()
    difficulty = declaration.get("difficulty")
    if skill and not isinstance(difficulty, (int, float)):
        issues.append(
            "work.%s declares skill '%s' but no difficulty, so the check it "
            "implies can never be rolled" % (work_id, skill)
        )
    if difficulty is not None and not skill:
        issues.append(
            "work.%s declares a difficulty but no skill, so nothing rolls it"
            % work_id
        )

    for field_name in ("inputs", "outputs"):
        entries = declaration.get(field_name)
        if entries is None:
            continue
        if not isinstance(entries, list):
            issues.append("work.%s %s must be a list" % (work_id, field_name))
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("item_id", "")).strip():
                issues.append(
                    "work.%s %s has an entry with no item_id" % (work_id, field_name)
                )
    # No check for "outputs is empty": work that only passes time is a legitimate
    # declaration (a door that unseals, a forge that cools), and the yield is a
    # field rather than the reason the timer exists.
    return issues


# --- the jobs a player carries -------------------------------------------------
# The four slots a caller installs timers into. Named once so the reader, the
# writer and the save agree about where a job lives.


def carried_jobs(player: Any) -> Optional[List[Dict[str, Any]]]:
    """The list this player's timers live in, or None when the game has no work.

    None is a *different* answer from an empty list: an empty list means "no jobs
    running", None means "this world does not present work at all", and a caller
    that conflates them tells a player their job vanished.
    """
    state = getattr(getattr(player, "runtime_state", None), "work", None)
    if state is None:
        return None
    jobs = getattr(state, "jobs", None)
    if not isinstance(jobs, list):
        state.jobs = []
        jobs = state.jobs
    return jobs


def due_jobs(world: Any, player: Any) -> List[Dict[str, Any]]:
    """Every carried timer the world clock has reached, in the order started."""
    jobs = carried_jobs(player) or []
    return [timer for timer in jobs if is_due(world, timer)]


def start(
    world: Any,
    player: Any,
    work_id: str,
    available_stations: Iterable[str] = (),
) -> Dict[str, Any]:
    """Begin `work_id` for `player`: consume its inputs, install its timer.

    Returns `{ok, message, timer}`; on refusal `{ok: False, message}` and nothing
    has changed -- every check happens before anything is spent, including the one
    that needs a clock to exist. That ordering is the whole contract: a refused
    start must not cost a player their materials.

    `available_stations` is the caller's answer to "what is here", because where a
    station *is* belongs to the game's room model rather than to a declaration
    about time. A declaration with no `station` needs none.
    """
    jobs = carried_jobs(player)
    if jobs is None:
        return _refusal("This game has nothing to work on.")

    declaration = work_for(world, work_id)
    if declaration is None:
        return _refusal("There is no such work here.")

    station = str(declaration.get("station", "") or "").strip()
    if station and station not in {str(entry).strip() for entry in available_stations}:
        return _refusal("You need a %s to start that." % _display(station))

    inventory = getattr(player, "inventory", None)
    if inventory is None:
        return _refusal("You have nowhere to work from.")

    # The timer first: an unreadable clock means nothing can take time here, and
    # finding that out after consuming the inputs would be theft.
    timer = begin(world, work_id, timer_id=_free_timer_id(jobs, work_id))
    if timer is None:
        return _refusal("Time is not passing here, so that cannot finish.")

    wanted: List[Any] = []
    for entry in _entries(declaration, "inputs"):
        item_id = str(entry.get("item_id", ""))
        quantity = _quantity(entry)
        chosen = inventory.select_items(item_id, quantity)
        if len(chosen) < quantity:
            return _refusal(
                "You need %d x %s." % (quantity, _item_name(world, item_id))
            )
        wanted.extend(chosen)

    outputs = _outputs(world, declaration)
    if outputs is None:
        return _refusal("That work names something this world does not have.")
    for item, quantity in outputs:
        fits, space_message = inventory.can_add_item_after_removing(item, quantity, wanted)
        if not fits:
            return _refusal(space_message)

    if wanted and not inventory.remove_item_instances(wanted):
        # Capacity was checked against this exact spend, so this needs an external
        # mutation to reach -- never report it as a successful start.
        return _refusal("The materials are no longer there.")

    jobs.append(timer)
    notes = _yield_note(declaration)
    return {
        "ok": True,
        "timer": timer,
        "message": "You start %s. %s" % (str(declaration.get("label", work_id)).lower(), notes),
    }


def collect(world: Any, player: Any, timer: Any) -> Dict[str, Any]:
    """Finish a due job: roll its check, yield its outputs, drop the timer.

    The roll happens here rather than at `start` because the check is about the
    *result*, not about whether the work was allowed to begin. A failed roll costs
    half the yield rather than everything: the inputs are already spent, and work
    that can vanish entirely is work nobody starts twice.

    A job whose outputs will not fit stays due and stays carried. Refusing is
    recoverable -- drop something and collect again -- where dropping the yield
    would not be.
    """
    jobs = carried_jobs(player)
    if jobs is None:
        return _refusal("This game has nothing to work on.")
    if timer not in jobs:
        return _refusal("That is not one of your jobs.")

    declaration = work_for(world, str(timer.get("work", "")) if isinstance(timer, dict) else "")
    if declaration is None:
        return _refusal("That job names work this world no longer declares.")

    if not is_due(world, timer):
        seen = observe(world, timer)
        left = seen.get("remaining_days")
        return _refusal(
            "%s is still running (%s left)."
            % (str(declaration.get("label", "That")), _days_phrase(left))
        )

    inventory = getattr(player, "inventory", None)
    if inventory is None:
        return _refusal("You have nowhere to put the result.")

    outputs = _outputs(world, declaration)
    if outputs is None:
        return _refusal("That work names something this world does not have.")

    roll_note = ""
    multiplier = 1.0
    skill = str(declaration.get("skill", "") or "").strip()
    difficulty = declaration.get("difficulty")
    if skill and isinstance(difficulty, (int, float)) and not isinstance(difficulty, bool):
        success, roll_note = _practice(player, skill, int(difficulty))
        if not success:
            multiplier = 0.5

    yielded: List[str] = []
    for item, quantity in outputs:
        wanted = quantity if multiplier >= 1.0 else max(1, quantity // 2)
        fits, space_message = inventory.can_add_item(item, wanted)
        if not fits:
            return _refusal("You have no room for the result: %s" % space_message)
        added, add_message = inventory.add_item(item, wanted)
        if not added:
            return _refusal("Unable to take the result: %s" % add_message)
        yielded.append("%d x %s" % (wanted, item.name))

    jobs.remove(timer)
    label = str(declaration.get("label", "the job"))
    # Work with no outputs is work that only passed time, and that is a declared
    # shape rather than a failure: say so instead of trailing an empty list.
    head = "You finish %s%s." % (
        label.lower(),
        ": " + ", ".join(yielded) if yielded else "",
    )
    if multiplier < 1.0:
        head += " It does not go well, and half of it is spoiled."
    return {
        "ok": True,
        "message": " ".join(part for part in (head, roll_note) if part),
        "yielded": yielded,
    }


def _practice(player: Any, skill: str, difficulty: int) -> Any:
    """The gameplay check, imported here so `work` has no skill system of its own.

    `practice_check` rather than `attempt_check`: a check that cannot raise what it
    tests is a gate a player can never grow past.
    """
    from engine.core.skill_system import SkillSystem

    return SkillSystem.practice_check(player, skill, difficulty)


def _refusal(reason: str) -> Dict[str, Any]:
    return {"ok": False, "message": reason}


def _entries(declaration: Dict[str, Any], field_name: str) -> List[Dict[str, Any]]:
    entries = declaration.get(field_name)
    if not isinstance(entries, list):
        return []
    return [
        entry for entry in entries
        if isinstance(entry, dict) and str(entry.get("item_id", "")).strip()
    ]


def _quantity(entry: Dict[str, Any]) -> int:
    quantity = entry.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        return 1
    return quantity


def _outputs(world: Any, declaration: Dict[str, Any]):
    """`[(item, quantity)]` for a declaration, or None when a template is missing.

    The items are built here rather than at collect time so the *capacity*
    question can be asked before anything is spent. Building an item does not
    place it anywhere.
    """
    from engine.items.item_factory import ItemFactory

    built = []
    for entry in _entries(declaration, "outputs"):
        item_id = str(entry.get("item_id", ""))
        item = ItemFactory.create_item_from_template(item_id, world)
        if item is None:
            return None
        built.append((item, _quantity(entry)))
    return built


def _free_timer_id(jobs: List[Dict[str, Any]], work_id: str) -> str:
    """A timer id nothing else on this player is using.

    Unique because a job's id is how a player names it back: two batches of the
    same work must be two jobs, and "collect the second one" has to be sayable.
    """
    taken = {str(timer.get("id", "")) for timer in jobs if isinstance(timer, dict)}
    base = str(work_id)
    if base not in taken:
        return base
    index = 2
    while "%s:%d" % (base, index) in taken:
        index += 1
    return "%s:%d" % (base, index)


def _item_name(world: Any, item_id: str) -> str:
    """A template's own name, or the id made readable.

    The fallback strips the `item_` prefix because that is what a player reads
    elsewhere (`combat_system.py`, `commands/crafting.py`); a missing template is
    a content bug the reference checks should catch, and until they do, this
    should not read as broken English in the meantime.
    """
    from engine.items.item_factory import ItemFactory

    template = ItemFactory.get_template(item_id, world)
    if isinstance(template, dict):
        name = str(template.get("name", "")).strip()
        if name:
            return name
    text = str(item_id)
    if text.startswith("item_") and len(text) > 5:
        text = text[5:]
    return _display(text)


def _display(name: str) -> str:
    text = str(name).replace("_", " ").strip()
    return text[:1].lower() + text[1:] if text else "station"


def _days_phrase(remaining_days: Any) -> str:
    if not isinstance(remaining_days, (int, float)):
        return "an unknown time"
    if remaining_days >= 1.0:
        return "%.1f days" % remaining_days
    hours = max(0.0, float(remaining_days)) * 24.0
    if hours >= 1.0:
        return "%.0f hours" % hours
    return "under an hour"


def _yield_note(declaration: Dict[str, Any]) -> str:
    """What a started job promises: the wait, and whether there is a yield at all.

    The `jobs` listing is where a player compares one job's yield against
    another's; this is the sentence they read at the moment they commit the
    materials, so it names the time rather than repeating the whole table.
    """
    has_outputs = bool(_entries(declaration, "outputs"))
    days = declaration.get("duration_days", 0)
    if isinstance(days, (int, float)) and not isinstance(days, bool) and days > 0:
        return "It will be ready in %s." % _days_phrase(float(days))
    return "It is done already." if has_outputs else ""


def _now(world: Any) -> Optional[float]:
    """The world's clock reading, or None when there is no readable clock.

    A world with no clock cannot have durations, and saying so is better than
    silently anchoring to wall time -- which would make a headless test
    unrepeatable and a single-player session disagree with itself.
    """
    clock = getattr(world, "clock", None)
    now = getattr(clock, "now", None)
    if not callable(now):
        return None
    try:
        return float(now())
    except (TypeError, ValueError):
        return None
