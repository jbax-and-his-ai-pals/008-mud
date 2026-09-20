#!/usr/bin/env python3
"""Play every shipped content set a little, and fail the build if it cannot.

The content-set validator reads files: it resolves references, checks types, and
proves a package is *well-formed*. It cannot tell you whether the game made from
it can be played. The two failures this exists for both validated perfectly:

* `orbital_salvage` enabled `salvage` and declared no salvage rule for any item,
  so every attempt in that set answered "You cannot salvage the X" -- a whole
  advertised system that did nothing.
* A `_comment` key at the top of a recipe file crashed the crafting loader and
  silently removed *every* recipe in that file. The file was valid JSON with
  valid references; there were simply no recipes.

So this boots each set for real and *does* things to it, using only what the set
itself declares -- the recipes it ships, the nodes it places, the NPCs it seats,
the abilities it registers. Nothing is hard-coded to a content id, because a
check that knows the answer cannot discover a new one.

What counts as failure is deliberately narrow. A command may answer anything it
likes, including a refusal, as long as the engine handled it: this looks for
unhandled failures and for whole systems that are silently empty.

    python toolkit/content_playability_check.py [--set ID] [--verbose]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

CONTENT_SETS_DIR = _REPO_ROOT / "content_sets"

# Commands every set must answer, whatever it declares. Written down because
# these are the ones a player types before knowing anything about the game.
UNIVERSAL = ("look", "status", "skills", "inventory", "nearby", "journal", "help")

# Phrases that mean a handler failed rather than answered. The first is the
# message `CommandProcessor` returns when a handler raises, so a silent crash
# cannot pass as a valid response.
FAILURE_SIGNATURES = (
    "Something went wrong running",
    "CRITICAL ERROR",
    "Unknown command:",
    "Traceback (most recent call last)",
)

# How many commands one set is allowed before the check stops. Bounded because a
# content set with two hundred NPCs should not turn a build step into a soak test.
MAX_COMMANDS = 90


class Finding:
    """One thing the check found, and whether it fails the build."""

    def __init__(self, content_set: str, command: str, message: str, fatal: bool = True) -> None:
        self.content_set = content_set
        self.command = command
        self.message = message
        self.fatal = fatal

    def __str__(self) -> str:
        return "[%s] %s: %s" % ("FAIL" if self.fatal else "WARN", self.command, self.message)


def content_sets() -> List[Path]:
    if not CONTENT_SETS_DIR.is_dir():
        return []
    return sorted(
        path for path in CONTENT_SETS_DIR.iterdir()
        if path.is_dir() and (path / "content_set.manifest.json").is_file()
    )


def _first_word(name: str) -> str:
    cleaned = str(name or "").strip()
    return cleaned.split()[0].lower() if cleaned else ""


# A plausible argument for a command that needs one, looked up in the content
# the set actually declares. Nothing here is an id: `kind` is a question, and the
# answer comes from the set.
def _argument_for(kind: str, world: Any) -> Optional[str]:
    templates = getattr(world, "item_templates", {}) or {}

    def first_template(predicate) -> Optional[str]:
        for template_id in sorted(templates):
            template = templates[template_id]
            if isinstance(template, dict) and predicate(template):
                name = _first_word(template.get("name", template_id))
                if name:
                    return name
        return None

    if kind == "recipe":
        crafting = getattr(getattr(world, "game", None), "crafting_manager", None)
        recipes = sorted(getattr(crafting, "recipes", {}) or {})
        return recipes[0] if recipes else None
    if kind == "gather":
        return first_template(lambda template: template.get("type") == "ResourceNode")
    if kind == "salvage":
        return first_template(lambda template: template.get("type") in ("Weapon", "Armor", "Junk"))
    if kind == "item":
        return first_template(lambda template: template.get("type") not in ("ResourceNode",))
    if kind == "ability":
        from engine.magic.spell_registry import SPELL_REGISTRY

        abilities = sorted(SPELL_REGISTRY)
        return abilities[0] if abilities else None
    if kind == "npc":
        npcs = getattr(world, "npcs", {}) or {}
        for npc_id in sorted(npcs):
            name = _first_word(getattr(npcs[npc_id], "name", ""))
            if name:
                return name
        return None
    return None


# What a no-argument command needs to be exercised at all. Commands absent from
# this table run bare -- which is what a player typing the command name does.
ARGUMENT_KIND: Dict[str, str] = {
    "craft": "recipe",
    "make": "recipe",
    "gather": "gather",
    "mine": "gather",
    "forage": "gather",
    "harvest": "gather",
    "salvage": "salvage",
    "breakdown": "salvage",
    "scrap": "salvage",
    "examine": "item",
    "appraise": "item",
    "get": "item",
    "take": "item",
    "drop": "item",
    "equip": "item",
    "wield": "item",
    "cast": "ability",
    "talk": "npc",
    "speak": "npc",
    "greet": "npc",
    "attack": "npc",
    "kill": "npc",
    "trade": "npc",
    "shop": "npc",
    "give": "item",
}


def _capability_commands(world: Any, registry: Dict[str, Any]) -> List[str]:
    """One representative of every command this set's capabilities turn on.

    Read from the command registry rather than written down here: a list of
    command names maintained by hand is a list that goes stale the first time a
    command is renamed, and the renamed one would stop being checked without
    anything saying so. (The first version of this file asked for `collections`
    and got "Unknown command" -- the command is `collection`.)
    """
    content_set = getattr(world, "content_set", None)
    capabilities = set(getattr(content_set, "capabilities", ()) or ())
    ruleset_systems = {"progression", "economy"}

    found: List[str] = []
    seen: set = set()
    for key, data in registry.items():
        name = str(data.get("name", ""))
        if not name or name in seen:
            continue
        required = data.get("content_capability")
        if required and required in capabilities:
            seen.add(name)
            found.append(name)
            continue
        system = data.get("ruleset_system")
        if system and system in ruleset_systems and world.ruleset_system_enabled(system):
            seen.add(name)
            found.append(name)
    return sorted(found)


def _reachable_room_commands(world: Any, player: Any) -> List[str]:
    """Walk the starting region one step at a time, using its own exits."""
    from engine.npcs.npc_factory import NPCFactory  # noqa: F401 - ensures registration

    commands: List[str] = []
    seen = set()
    region = world.regions.get(player.current_region_id)
    if region is None:
        return commands
    room = region.rooms.get(player.current_room_id)
    if room is None:
        return commands
    for direction in list(getattr(room, "exits", {}) or {}):
        if direction in seen:
            continue
        seen.add(direction)
        commands.extend([direction, "look", "nearby"])
    return commands


def build_plan(content_set_path: Path, world: Any, player: Any, registry: Dict[str, Any]) -> List[str]:
    """What to type at this set, derived from what the set declares."""
    plan: List[str] = []

    # Every command this set's capabilities turn on, exercised with an argument
    # drawn from its own content where one is needed. This is the part that
    # reaches systems a hand-written list would forget: a set's salvage, its
    # abilities, its collections.
    for command in _capability_commands(world, registry):
        kind = ARGUMENT_KIND.get(command)
        if kind is None:
            plan.append(command)
            continue
        argument = _argument_for(kind, world)
        if argument:
            plan.append("%s %s" % (command, argument))

    # The commands every set must answer, whatever it declares.
    plan = list(UNIVERSAL) + plan

    plan.extend(_reachable_room_commands(world, player))

    # Abilities the set registers, in case the command table did not reach them.
    from engine.magic.spell_registry import SPELL_REGISTRY

    ability_ids = sorted(SPELL_REGISTRY)
    if ability_ids and "abilities" not in plan:
        plan.append("abilities")
    plan.extend("cast %s" % ability_id for ability_id in ability_ids[:6])

    # Resource nodes the set places, gathered with whatever is in hand.
    nodes = [
        template_id for template_id, template in (getattr(world, "item_templates", {}) or {}).items()
        if isinstance(template, dict) and template.get("type") == "ResourceNode"
    ]
    if nodes:
        plan.append("survey")
        for template_id in sorted(nodes)[:4]:
            template = world.item_templates[template_id]
            plan.append("gather %s" % _first_word(template.get("name", template_id)))

    # Deduplicate while keeping the order, and stop at the bound.
    ordered: List[str] = []
    for command in plan:
        if command and command not in ordered:
            ordered.append(command)
    return ordered[:MAX_COMMANDS]


def check_one(content_set_path: Path, verbose: bool = False) -> List[Finding]:
    """Boot one content set, play it, and report what broke."""
    from engine.commands.command_system import registered_commands
    from engine.server.headless_server import HeadlessServer

    findings: List[Finding] = []
    name = content_set_path.name

    try:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(content_set_path),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
    except Exception as error:  # a set that cannot boot is the loudest failure
        return [Finding(name, "boot", "%s: %s" % (type(error).__name__, error))]

    try:
        session = server.create_session(player_id="playability")
        created = _text(server, session.session_id, "char create Probe")
        if "created" not in created.lower() and "welcome" not in created.lower():
            findings.append(Finding(name, "char create", "a new character was not created: %s" % created[:200]))
            return findings

        player = server.get_player_for_session(session.session_id)
        if player is None:
            findings.append(Finding(name, "char create", "no player after character creation"))
            return findings

        # The engine's own definition stats: a directory that loaded zero files
        # when the capability says it should have is a silently empty system.
        findings.extend(_definition_findings(name, server, content_set_path))

        plan = build_plan(content_set_path, server.world, player, registered_commands)
        for command in plan:
            text = _text(server, session.session_id, command)
            if verbose:
                print("    > %-28s %s" % (command, text.splitlines()[0][:90] if text else "(no output)"))
            for signature in FAILURE_SIGNATURES:
                if signature in text:
                    findings.append(Finding(name, command, text.strip()[:300]))
                    break
            if _is_exerciseable(command) and not text.strip():
                findings.append(Finding(
                    name, command,
                    "answered with nothing at all -- a command that says nothing is "
                    "indistinguishable from one that is not there",
                ))
    finally:
        server.shutdown()

    return findings


def _definition_findings(name: str, server: Any, content_set_path: Path) -> List[Finding]:
    """A declared system that loaded nothing is a finding, not a detail."""
    findings: List[Finding] = []
    stats = getattr(server.world, "definition_load_stats", {}) or {}

    spell_stats = stats.get("spell_registry", {})
    if isinstance(spell_stats, dict) and spell_stats.get("enabled"):
        if int(spell_stats.get("spells_loaded", 0)) == 0:
            findings.append(Finding(
                name, "abilities", "the set declares abilities and loaded no ability definitions",
            ))
        if int(spell_stats.get("file_errors", 0)) > 0:
            findings.append(Finding(
                name, "abilities", "%d ability file(s) failed to load" % int(spell_stats["file_errors"]),
            ))

    item_stats = stats.get("item_templates", {})
    if isinstance(item_stats, dict):
        if int(item_stats.get("file_errors", 0)) > 0:
            findings.append(Finding(
                name, "items", "%d item file(s) failed to load" % int(item_stats["file_errors"]),
            ))
        if int(item_stats.get("invalid_missing_required", 0)) > 0:
            findings.append(Finding(
                name, "items",
                "%d item template(s) skipped for missing required fields" % int(item_stats["invalid_missing_required"]),
            ))

    npc_stats = stats.get("npc_templates", {})
    if isinstance(npc_stats, dict) and int(npc_stats.get("file_errors", 0)) > 0:
        findings.append(Finding(
            name, "npcs", "%d NPC file(s) failed to load" % int(npc_stats["file_errors"]),
        ))

    crafted = getattr(getattr(server.world, "game", None), "crafting_manager", None)
    if crafted is not None:
        declared = _declared_recipe_ids(content_set_path)
        loaded = set(getattr(crafted, "recipes", {}) or {})
        missing = sorted(declared - loaded)
        if missing:
            # A recipe the file declares and the loader did not produce. This is
            # the shape of the bug this whole check was written for: one bad key
            # in a recipe file aborted the file and every recipe in it vanished,
            # while the file stayed valid JSON with valid references.
            findings.append(Finding(
                name, "recipes",
                "%d recipe(s) declared in content did not load: %s"
                % (len(missing), ", ".join(missing[:6])),
            ))

    # A warning, not a failure, and the distinction is deliberate. An ability
    # with no player route is authored content that is not reachable *yet* --
    # a spell waiting for the vendor, the trainer or the quest that will teach
    # it. That is a content gap to see, not a build to stop: the shipped set has
    # several, each one cast by an NPC in the meantime. What must not happen is
    # it going unnoticed, which is what "nothing reads it" meant before this.
    #
    # Guarded on the set's own capability rather than on the registry being
    # non-empty. `SPELL_REGISTRY` is process-wide and this check boots every set
    # in one process, so the fantasy set's spells are still in it while the
    # sci-fi sets are being played -- which read as "23 of 23 abilities have no
    # route to the player" for a set that declares no abilities at all.
    if getattr(server.world, "uses_abilities", lambda: False)():
        from engine.magic.spell_registry import SPELL_REGISTRY

        declared_abilities = {str(spell_id) for spell_id in SPELL_REGISTRY}
        if declared_abilities:
            taught = _taught_ability_ids(server, content_set_path)
            never_taught = sorted(declared_abilities - set(taught))
            if never_taught:
                findings.append(Finding(
                    name, "abilities",
                    "%d of %d abilities have no route to the player (no scroll teaches "
                    "them, no background grants them, the ruleset does not start with "
                    "them): %s" % (
                        len(never_taught), len(declared_abilities),
                        ", ".join(never_taught[:8]) + ("…" if len(never_taught) > 8 else ""),
                    ),
                    fatal=False,
                ))
    return findings


def _declared_recipe_ids(content_set_path: Path) -> set:
    """Recipe ids named in the set's crafting files, notes excluded.

    A recipe whose value is not an object still counts as *declared*: the file
    says a recipe by that name is here, and the loader's job is to produce it.
    Notes are keyed with a leading underscore, which is how every loader in the
    engine tells content from commentary.
    """
    import json

    declared: set = set()
    crafting = content_set_path / "data" / "crafting"
    if not crafting.is_dir():
        return declared
    for path in sorted(crafting.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for recipe_id in payload:
            if not str(recipe_id).startswith("_"):
                declared.add(str(recipe_id))
    return declared


def _procedural_spell_route(server: Any, content_root: Path) -> Optional[str]:
    """Whether content ships an item that rolls a random learnable spell.

    This is the route the static scan cannot see, and missing it made this check
    report a false positive: `item_scroll_random` carries
    `properties.procedural_type: random_spell_scroll`, and `ItemFactory` fills it
    from **every** registered spell with `level_required > 0 and mana_cost > 0`
    (`items/item_factory.py:161`). So one authored template makes most of a set's
    abilities reachable, and a scan that only reads `spell_to_learn` will call
    them dead.

    It returns the item id rather than a bool so the finding can say which
    template is doing the work -- otherwise the next reader of this file will
    make the same mistake the first version did.
    """
    import json

    for path in sorted(content_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for entry_id, entry in payload.items():
            if str(entry_id).startswith("_") or not isinstance(entry, dict):
                continue
            properties = entry.get("properties")
            if not isinstance(properties, dict):
                continue
            if str(properties.get("procedural_type", "")) == "random_spell_scroll":
                return str(entry_id)
    return None


def _taught_ability_ids(server: Any, content_set_path: Path) -> set:
    """Ability ids a player has a route to, and how: `{id: route}`.

    Four routes exist today, and all four are content:

    * a scroll or tome an item teaches (`properties.spell_to_learn`), which the
      consumable hands to the player when used;
    * a **procedural** scroll (`properties.procedural_type:
      random_spell_scroll`), which rolls over every spell the factory admits --
      one template, most of the set's abilities;
    * a background that starts the character knowing it (`spells`);
    * the ruleset's own starting list (`player_defaults.magic.known_spells`).

    The engine also puts spells on NPCs (`usable_spells`, `random_spells.pool`)
    so they can cast at you, which is a real and reachable use for a template --
    but it is not a route for the *player*, so it does not count here. That
    distinction is the whole reason this is a warning and not an error: an
    ability only ever cast by an NPC is authored deliberately, whereas an
    ability nothing anywhere names is usually a spell somebody meant to stock a
    vendor with and did not.
    """
    import json

    taught: dict = {}
    content_root = content_set_path / "data"

    for path in sorted(content_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        relative = path.relative_to(content_root).as_posix()
        for entry_id, entry in payload.items():
            if str(entry_id).startswith("_") or not isinstance(entry, dict):
                continue
            properties = entry.get("properties")
            if isinstance(properties, dict) and isinstance(properties.get("spell_to_learn"), str):
                learned = properties["spell_to_learn"].strip()
                if learned:
                    taught.setdefault(learned, "taught by %s" % relative)
            if "backgrounds" in relative:
                for spell_id in entry.get("spells", []) or []:
                    if isinstance(spell_id, str) and spell_id.strip():
                        taught.setdefault(spell_id.strip(), "a starting background")

    ruleset_dir = content_set_path / "rules"
    for path in sorted(ruleset_dir.glob("*.json")) if ruleset_dir.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        defaults = payload.get("player_defaults") if isinstance(payload, dict) else None
        magic = defaults.get("magic") if isinstance(defaults, dict) else None
        for spell_id in (magic.get("known_spells", []) if isinstance(magic, dict) else []) or []:
            if isinstance(spell_id, str) and spell_id.strip():
                taught.setdefault(spell_id.strip(), "the ruleset's starting spells")

    # A procedural scroll makes every spell the factory admits reachable, so it
    # has to be resolved against the registry rather than read as a name. Without
    # this the check called 16 of fantasy's 23 abilities dead when 20 are on one
    # vendor's shelf.
    procedural = _procedural_spell_route(server, content_root)
    if procedural is not None:
        from engine.magic.spell_registry import SPELL_REGISTRY

        for spell_id, spell in SPELL_REGISTRY.items():
            if getattr(spell, "level_required", 0) > 0 and getattr(spell, "mana_cost", 0) > 0:
                taught.setdefault(str(spell_id), "rolled by %s" % procedural)
    return taught


# Commands that are a question about state, and answering nothing is a defect.
# A command that takes an argument it did not get may legitimately answer nothing
# to a prompt-free caller, so only the bare state questions are held to this.
_EXERCISEABLE = frozenset(UNIVERSAL) | {"abilities", "recipes", "orders", "quests"}


def _is_exerciseable(command: str) -> bool:
    return command in _EXERCISEABLE


def _text(server: Any, session_id: str, command: str) -> str:
    events = server.execute_command(session_id, command)
    return "\n".join(
        str(event.get("payload"))
        for event in events
        if event.get("type") in ("text", "error")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="only", default=None, help="limit to one content set id")
    parser.add_argument("--verbose", action="store_true", help="print every command and its answer")
    args = parser.parse_args()

    sets = content_sets()
    if args.only:
        sets = [path for path in sets if path.name == args.only]
    if not sets:
        print("No content sets found under %s." % CONTENT_SETS_DIR)
        return 2

    all_findings: List[Finding] = []
    for content_set in sets:
        print("==> Playing %s" % content_set.name)
        findings = check_one(content_set, verbose=args.verbose)
        all_findings.extend(findings)
        if not findings:
            print("OK: %s can be played" % content_set.name)
        else:
            for finding in findings:
                print("    %s" % finding)

    fatal = [finding for finding in all_findings if finding.fatal]
    print()
    if fatal:
        print("%d playability finding(s) across %d set(s)." % (len(fatal), len(sets)))
        return 1
    print("Every content set can be played.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
