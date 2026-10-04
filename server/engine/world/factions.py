# engine/world/factions.py
"""Who is on whose side, asked in one place.

`config_world.FACTION_RELATIONSHIP_MATRIX` has always held the answer, and
`npcs/combat.py` already attacks by it. What it did not have was *readers*: two
dozen other call sites asked the question by comparing a faction string to
`"hostile"` -- for room descriptions, target lists, conversation gating, wander
destinations, quest generation, reputation on a kill. That works for the five
built-in names and it is wrong for every other world: a content set whose raiders
are called `the_cold_ones` gets NPCs that never look dangerous, never flee toward
danger, are offered as conversation partners, and pay no reputation when killed,
because no string comparison anywhere says `"hostile"`.

So the vocabulary is a **declaration**, with the engine's five as its default:

    ruleset.json
      "factions": {
        "extra": [
          {"id": "raiders", "disposition": "hostile"},
          {"id": "townsfolk", "disposition": "friendly"}
        ],
        "overrides": {"neutral": "friendly"}
      }

A disposition is one of `FACTION_DISPOSITIONS` -- `hostile`, `friendly`,
`neutral`, `player` -- and it decides three things at once: whether the faction
fights the player, whether it can be talked to, and what killing one does to
reputation. A set that only renames its enemies declares one line and every call
site follows, because none of them compares strings any more.

Attitudes stay in the matrix (`attitude`), so a set can still be specific about
who ignores whom; the derived rows below are only how a disposition expands into
one. The engine's own five rows are unchanged, which is what keeps this a
refactor rather than a balance change.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.config import FACTION_DISPOSITIONS, FACTION_DISPOSITION_ROWS

# The matrix row shape: how `viewer` feels about each faction, -100 (attacks on
# sight) through 0 (ignores) to 100 (allied).
PLAYER_FACTION = "player"


def _ruleset_factions(world) -> Dict[str, Any]:
    if world is None:
        return {}
    getter = getattr(world, "ruleset_section", None)
    if not callable(getter):
        return {}
    section = getter("factions")
    return section if isinstance(section, dict) else {}


class RulesetView:
    """A `world`-shaped reader over a raw ruleset payload.

    Validation runs before a world exists, and it has to ask the same questions a
    live world asks. Rather than a second reading of the section in the validator
    -- the drift this module exists to prevent -- the payload is wrapped in the
    one method the readers use.
    """

    def __init__(self, payload: Optional[Dict[str, Any]]):
        self._payload = payload if isinstance(payload, dict) else {}

    def ruleset_section(self, name: str) -> Dict[str, Any]:
        if name != "factions":
            return {}
        section = self._payload.get("factions", self._payload)
        return section if isinstance(section, dict) else {}


def declared_extras(world) -> List[Dict[str, Any]]:
    """`factions.extra` entries, in authored order, ignoring unusable ones."""
    raw = _ruleset_factions(world).get("extra", [])
    if not isinstance(raw, list):
        return []
    entries: List[Dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict) and str(entry.get("id", "")).strip():
            entries.append(entry)
    return entries


def declared_enmities(world) -> List[Dict[str, str]]:
    """`factions.enmities`: `{faction, against}` pairs, in authored order, ignoring unusable ones.

    Dispositions say how a faction treats the player and what the engine's own five think of it; an enmity says one
    faction attacks another on sight (soldiers and the acolytes they came for) without either one turning hostile
    to the player. It is one-way: the faction named `against` does not return it unless it declares the same."""
    raw = _ruleset_factions(world).get("enmities", [])
    if not isinstance(raw, list):
        return []
    found: List[Dict[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict) and str(entry.get("faction", "")).strip() and str(entry.get("against", "")).strip():
            found.append({"faction": str(entry["faction"]).strip(), "against": str(entry["against"]).strip()})
    return found


def declared_overrides(world) -> Dict[str, str]:
    """`factions.overrides`: built-in id -> disposition, ignoring unusable ones."""
    raw = _ruleset_factions(world).get("overrides", {})
    if not isinstance(raw, dict):
        return {}
    overrides: Dict[str, str] = {}
    for faction_id, disposition in raw.items():
        if isinstance(disposition, str) and disposition.strip():
            overrides[str(faction_id).strip()] = disposition.strip()
    return overrides


def dispositions(world=None) -> Dict[str, str]:
    """Every declared faction and the disposition it was given.

    The engine's five come first so a set's own names can never redefine what
    `friendly` means by accident -- that takes an explicit `overrides` entry.
    """
    from engine.config import FACTIONS

    resolved: Dict[str, str] = {}
    overrides = declared_overrides(world)
    for faction_id in FACTIONS:
        resolved[faction_id] = overrides.get(faction_id, _default_disposition(faction_id))
    for entry in declared_extras(world):
        faction_id = str(entry["id"]).strip()
        disposition = str(entry.get("disposition", "")).strip()
        if disposition:
            resolved[faction_id] = disposition
    return resolved


def _default_disposition(faction_id: str) -> str:
    from engine.config import FACTION_DEFAULT_DISPOSITIONS

    return FACTION_DEFAULT_DISPOSITIONS.get(faction_id, "neutral")


def factions(world=None) -> List[str]:
    return sorted(dispositions(world))


def _row_for(disposition: str) -> Dict[str, int]:
    return dict(FACTION_DISPOSITION_ROWS.get(disposition, FACTION_DISPOSITION_ROWS["neutral"]))


def matrix(world=None) -> Dict[str, Dict[str, int]]:
    """The attitude matrix this world plays by: the engine's five, resolved.

    A faction with a non-default disposition (a set's own name, or an override)
    gets that disposition's row, with the disposition's *own* value standing in
    for the new name -- so two hostile kinds ignore each other (`hostile`'s row
    says 0 about itself, and goblins have never fought wolves), while two
    friendly kinds are allied (100 about itself).
    """
    resolved = dispositions(world)
    rows: Dict[str, Dict[str, int]] = {}
    for faction_id, disposition in resolved.items():
        row = _row_for(disposition)
        for other_id in resolved:
            row.setdefault(other_id, int(row.get(resolved[other_id], 0)))  # an unnamed faction is felt about as its disposition is
        row[faction_id] = int(row.get(disposition, 0))
        rows[faction_id] = row
    for entry in declared_enmities(world):
        viewer, target = entry["faction"], entry["against"]
        if viewer in rows and target in rows and viewer != target:
            rows[viewer][target] = -100
    return rows


def faction_of(actor: Any) -> str:
    """The faction id of an actor, an NPC template dict, or a faction string."""
    if actor is None:
        return ""
    if isinstance(actor, str):
        return actor.strip()
    if isinstance(actor, dict):
        return str(actor.get("faction", "") or "").strip()
    return str(getattr(actor, "faction", "") or "").strip()


def attitude(world, viewer: Any, target: Any) -> int:
    """How `viewer` feels about `target`, from the matrix alone.

    Deliberately without the player-reputation modifier: `npcs/combat.py`'s
    `get_relation_to` adds that where a fight is being decided. This is the
    coarse question -- "is this thing on my side at all" -- asked by display,
    gating and generation code that has no fight in front of it.
    """
    viewer_faction = faction_of(viewer)
    target_faction = faction_of(target)
    if not viewer_faction or not target_faction:
        return 0
    row = matrix(world).get(viewer_faction)
    if not isinstance(row, dict):
        return 0
    value = row.get(target_faction, 0)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def disposition_of(actor: Any, world=None) -> str:
    """Which side an actor is on, coarsely: `hostile`, `friendly`, `neutral`, `player`."""
    return dispositions(world).get(faction_of(actor), "")


def is_hostile(actor: Any, world=None) -> bool:
    """Whether this actor is an enemy of the player.

    The question almost every call site meant by `faction == "hostile"`.
    """
    return attitude(world, actor, PLAYER_FACTION) < 0


def hostiles_in(world, region_id: str, room_id: str) -> List[Any]:
    """The living hostile NPCs standing in a room.

    What "the room is cleared" means, for the `room_clear` condition and for anything
    else that asks it. A friendly, a summoned ally and a corpse do not count.
    """
    if world is None:
        return []
    return [
        npc for npc in getattr(world, "npcs", {}).values()
        if getattr(npc, "is_alive", False)
        and (getattr(npc, "current_region_id", None), getattr(npc, "current_room_id", None)) == (region_id, room_id)
        and is_hostile(npc, world)
    ]


def is_friendly(actor: Any, world=None) -> bool:
    return disposition_of(actor, world) == "friendly"


def is_player_side(actor: Any, world=None) -> bool:
    """The player, and anything summoned to fight for them."""
    return disposition_of(actor, world) == "player"


def same_faction(first: Any, second: Any) -> bool:
    """Whether two actors share a faction id -- the infighting rule."""
    first_faction = faction_of(first)
    return bool(first_faction) and first_faction == faction_of(second)


def can_converse(actor: Any, world=None) -> bool:
    """Whether an actor is somebody you can talk to.

    An enemy is not, and neither is a summoned minion: it may be on your side,
    but it is not a person with something to say.
    """
    if is_hostile(actor, world) or is_player_side(actor, world):
        return False
    properties = getattr(actor, "properties", None)
    if isinstance(properties, dict) and properties.get("is_summoned"):
        return False
    return bool(faction_of(actor))


def issues(world=None) -> List[str]:
    """Authoring problems in the `factions` section, for the content gate.

    Kept here rather than in the validator so the shape and its refusals live
    together; `content_set/` turns these into content issues with a path.
    """
    found: List[str] = []
    from engine.config import FACTIONS

    seen: Dict[str, int] = {}
    for index, entry in enumerate(declared_extras(world)):
        label = "factions.extra[%d]" % index
        faction_id = str(entry.get("id", "")).strip()
        if not faction_id:
            found.append("%s must name an id" % label)
            continue
        if faction_id in FACTIONS:
            found.append(
                "%s names '%s', which is an engine faction; use factions.overrides to restate it"
                % (label, faction_id)
            )
        seen[faction_id] = seen.get(faction_id, 0) + 1
        disposition = str(entry.get("disposition", "")).strip()
        if not disposition:
            found.append("%s ('%s') must declare a disposition" % (label, faction_id))
        elif disposition not in FACTION_DISPOSITIONS:
            found.append(
                "%s ('%s').disposition %r is not one of %s"
                % (label, faction_id, disposition, ", ".join(FACTION_DISPOSITIONS))
            )
    for faction_id, count in seen.items():
        if count > 1:
            found.append("factions.extra declares '%s' %d times" % (faction_id, count))

    known = set(dispositions(world))
    raw_enmities = _ruleset_factions(world).get("enmities", [])
    if raw_enmities is not None and not isinstance(raw_enmities, list):
        found.append("factions.enmities must be an array")
    elif isinstance(raw_enmities, list):
        for index, entry in enumerate(raw_enmities):
            label = "factions.enmities[%d]" % index
            if not isinstance(entry, dict):
                found.append("%s must be an object {faction, against}" % label)
                continue
            for key in ("faction", "against"):
                value = str(entry.get(key, "") or "").strip()
                if not value:
                    found.append("%s must name a %s" % (label, key))
                elif value not in known:
                    found.append("%s.%s names '%s', which is not a declared faction" % (label, key, value))
            if str(entry.get("faction", "")).strip() and entry.get("faction") == entry.get("against"):
                found.append("%s makes a faction an enemy of itself" % label)

    raw_extras = _ruleset_factions(world).get("extra", [])
    if raw_extras is not None and not isinstance(raw_extras, list):
        found.append("factions.extra must be an array")
    raw_overrides = _ruleset_factions(world).get("overrides", {})
    if raw_overrides is not None and not isinstance(raw_overrides, dict):
        found.append("factions.overrides must be an object")
    elif isinstance(raw_overrides, dict):
        for faction_id, disposition in raw_overrides.items():
            if faction_id not in FACTIONS:
                found.append(
                    "factions.overrides names '%s', which is not an engine faction; "
                    "declare it in factions.extra instead" % faction_id
                )
            if disposition not in FACTION_DISPOSITIONS:
                found.append(
                    "factions.overrides['%s'] %r is not one of %s"
                    % (faction_id, disposition, ", ".join(FACTION_DISPOSITIONS))
                )
    return found


def describe(world=None) -> str:
    """A test-mode summary: one line per faction and what it thinks of you."""
    lines = []
    for faction_id in factions(world):
        lines.append(
            "%-16s %-9s attitude to player: %+d"
            % (faction_id, dispositions(world)[faction_id], attitude(world, faction_id, PLAYER_FACTION))
        )
    return "\n".join(lines)
