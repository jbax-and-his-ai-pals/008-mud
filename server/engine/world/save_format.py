# engine/world/save_format.py
"""What a save file's `save_format_version` means, and how an old one is read.

A save is a snapshot of state that code has since moved on from. The version
stamp is what makes that legible: without it, a reader can only guess whether a
missing key means "written before this existed" or "written by something that
meant something else by it", and guessing is how a load silently produces a
half-restored character instead of saying so.

Two rules make this worth having at all:

* **One version, one meaning.** `SAVE_FORMAT_VERSION` is the version this engine
  *writes*. A file stamped higher was written by a newer engine, and this one
  refuses it rather than reading the parts it recognises and defaulting the rest.
  Refusing is recoverable; a character that loaded "successfully" is not.
* **Migrations move state, not keys.** Each entry in `MIGRATIONS` describes what
  changed between two versions and returns the state that version's reader
  expected. A version bump that needs no migration is still recorded, because
  the next person needs to know *why* it was safe.

A save from before the stamp existed -- there was no `save_format_version` at all
-- is read as `UNVERSIONED`, which is treated as version 1: the state the earliest
saves actually carried.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# The version this engine writes. Bump it whenever a change makes an older save
# mean something different, and add a migration below in the same commit.
SAVE_FORMAT_VERSION = 4

# A save with no stamp at all. Older than any version number.
UNVERSIONED = 0


def declared_version(save_data: Any) -> int:
    """The version a save declares, or `UNVERSIONED` when it declares none."""
    if not isinstance(save_data, dict):
        return UNVERSIONED
    raw = save_data.get("save_format_version")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        # A stamp that is not a number is not evidence of anything. Treat it as
        # the oldest readable format rather than rejecting the whole file -- the
        # migrations below are the ones that know what an old file looks like.
        return UNVERSIONED
    return int(raw)


def _migrate_1_to_2(save_data: Dict[str, Any]) -> Dict[str, Any]:
    """Saves stopped being interchangeable between content sets.

    Version 1 files were written before a save recorded which game it belonged
    to. The state is unchanged; what changed is that a reader now checks.
    """
    return save_data


def _migrate_2_to_3(save_data: Dict[str, Any]) -> Dict[str, Any]:
    """A save records the content set and version it was written against.

    Nothing to move: a version 2 file has no such record, and a reader that
    cannot find one has always tolerated that.
    """
    return save_data


def _migrate_3_to_4(save_data: Dict[str, Any]) -> Dict[str, Any]:
    """Summoned NPCs stopped being reloadable, and the summon list with them.

    A summoned NPC carries the state that makes it a summon -- how long it has
    left, when it was made -- in its own `properties`, and `NPC.to_dict` does not
    persist properties. So a saved summon always came back as an ordinary
    creature of its template: it would never expire, and the player's record of
    having summoned it would have pointed at an id that no longer meant the same
    thing. Since version 4 the list travels *within one running game*; a save is
    not a place it can survive.

    Version 3 files are from before any of this was written down, so their
    summon list is stale by definition. The flag lives on the player payload
    because that is the object whose reader knows what a summon list is.
    """
    player = save_data.get("player")
    if isinstance(player, dict):
        player[STALE_SUMMONS_KEY] = True
    return save_data


# (from_version, to_version) -> what changed. Applied in order, so a version 1
# file passes through every entry on its way to the current version.
MIGRATIONS: Dict[Tuple[int, int], Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    (1, 2): _migrate_1_to_2,
    (2, 3): _migrate_2_to_3,
    (3, 4): _migrate_3_to_4,
}


# Set on a player payload by a migration that decided its summon list is stale.
# A private key: it never reaches a file, and `Player.from_dict` consumes it.
STALE_SUMMONS_KEY = "_stale_summons"


class UnsupportedSaveVersion(Exception):
    """A save this engine will not read, and why."""

    def __init__(self, message: str, version: int) -> None:
        super().__init__(message)
        self.version = version


def migrate(save_data: Any, target: int = SAVE_FORMAT_VERSION) -> Tuple[Dict[str, Any], List[str]]:
    """Bring a save up to `target`, returning it and a log of what was applied.

    Raises `UnsupportedSaveVersion` for a save from the future: a newer format is
    the one case where reading what we recognise and defaulting the rest would
    quietly discard a player's progress.
    """
    if not isinstance(save_data, dict):
        raise UnsupportedSaveVersion("A save must be a JSON object", UNVERSIONED)
    version = declared_version(save_data)
    if version > target:
        raise UnsupportedSaveVersion(
            "This save was written by a newer version of the game "
            "(save format %d; this build reads up to %d). Update the game to "
            "load it." % (version, target),
            version,
        )

    applied: List[str] = []
    current = version
    while current < target:
        step = MIGRATIONS.get((current, current + 1))
        if step is None:
            # A version gap with no migration is a missing entry, not a reason
            # to refuse: the reader tolerates absent keys, so the file is read as
            # it is and the gap is reported.
            applied.append("no migration recorded from %d to %d" % (current, current + 1))
        else:
            save_data = step(save_data)
            applied.append(step.__name__)
        current += 1
    return save_data, applied


def take_stale_summons_flag(player_data: Any) -> bool:
    """Whether a migration decided this player's summon list is stale.

    Consumed by `Player.from_dict`, which is the only reader that knows what a
    summon list is. Removes the key either way, so it never reaches a re-save.
    """
    return bool(isinstance(player_data, dict) and player_data.pop(STALE_SUMMONS_KEY, False))
