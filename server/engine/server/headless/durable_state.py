"""A single-player game that remembers itself.

Until this existed the running server persisted nothing: both transports built an
in-memory database, a character was written after every command and never read back,
and a returning player could not be told from a new one. This mixin is the part of the
server that closes that.

**Who it is for.** Only a single-player world (`single_player_story`,
`finite_adventure`), because there identity is trivial: the game has one character, so
"resume by name" is a light confirmation and not a login. A shared world (`persistent_shard`
and the rest) is left exactly as it was, because a name is not an identity there and
nobody has decided what is (chunks-of-work.md, Decision 7).

**What it keeps.** Two records in the game's own SQLite file. The character
(`character:<name>`) is written after every command, as it always was. The world is
`world_snapshot.capture` under one key, autosaved on an interval, when a session
disconnects, and at shutdown, with an envelope naming the content set and version it
belongs to. A save that belongs to a different game or version is never read and never
written over: the server carries on without persistence and says why.

**Time.** A restart starts the world's clock again, or a wall clock kept running while
the server was stopped. The world snapshot stores deadlines as time remaining, and the
character record carries the clock reading it was written at, so `shift_deadlines`
can move the player's few absolute readings onto the new clock. Downtime does not count.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any, Dict, List, Optional

from engine.player.deadlines import shift_deadlines
from engine.server.persistence.paths import default_database_path
from engine.server.persistence.sqlite_store import SqliteStore
from engine.utils.logger import Logger
from engine.world import world_snapshot
from engine.world.save_format import SAVE_FORMAT_VERSION

# The world modes with exactly one character in one world.
DURABLE_WORLD_MODES = frozenset({"single_player_story", "finite_adventure"})

WORLD_STATE_KEY = "world"
CHARACTER_ENTITY_TYPE = "character"
# Seconds of world-clock time between autosaves of the world. The character is written
# after every command regardless; this only paces the world, which a full snapshot of
# the largest shipped set makes cheap (about 5 ms) but not free.
AUTOSAVE_INTERVAL_SECONDS = 5.0


def _normalized(name: Any) -> str:
    return " ".join(str(name).lower().split())


class DurableStateMixin:
    # -- choosing whether to persist, before the store exists ---------------------------

    def _plan_persistence(self, db_path: Optional[str], ephemeral: bool, new_game: bool) -> str:
        """Decide whether this server keeps its game, and where. Returns the path to open.

        `self.feature_profile` and `self.content_set` must already exist. Sets
        `self.durable_persistence`.
        """
        self.persistence_notices: List[str] = []
        mode = self.feature_profile.resolved_world_mode()
        capable = mode in DURABLE_WORLD_MODES
        explicit_memory = db_path == ":memory:"
        if ephemeral or explicit_memory or not capable:
            # Everything that was true before: a shared world, a test, or a player who
            # asked for nothing to be kept. Write-only, in memory unless a path was given.
            self.durable_persistence = False
            if ephemeral or explicit_memory:
                return ":memory:"
            return db_path or ":memory:"
        path = db_path or default_database_path(self.content_set.content_set_id)
        self.durable_persistence = True
        if new_game:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(path + suffix)
                except FileNotFoundError:
                    pass
        self._last_autosave_at = 0.0
        return path

    def _content_identity(self) -> Dict[str, str]:
        return {
            "id": str(getattr(self.content_set, "content_set_id", "")).strip(),
            "version": str(getattr(self.content_set, "version", "")).strip(),
        }

    def _refuse_persistence(self, why: str) -> None:
        """Carry on without persistence, leaving a save this server cannot read untouched."""
        Logger.error("DurableState", why)
        self.persistence_notices.append(why)
        self.durable_persistence = False
        self.persistence.close()
        self.persistence = SqliteStore(":memory:")
        self.persistence.start_async_writer()

    # -- restoring the world at boot -----------------------------------------------------

    def _restore_durable_world(self) -> None:
        """Put the saved world back. Called once the world, the clock and the fields exist."""
        if not self.durable_persistence:
            return
        record = self.persistence.load_world_state(WORLD_STATE_KEY)
        if record is None:
            self._last_autosave_at = float(self.world.clock.now())
            return
        envelope = record.get("envelope") or {}
        saved = envelope.get("content_set") or {}
        current = self._content_identity()
        saved_format = envelope.get("save_format_version", 0)
        if (
            saved.get("id") != current["id"]
            or saved.get("version") != current["version"]
            or (isinstance(saved_format, int) and saved_format > SAVE_FORMAT_VERSION)
        ):
            self._refuse_persistence(
                "The saved game belongs to %s@%s (save format %s), not to %s@%s (format %d). It has been left "
                "untouched and this session will not be saved. Start over with --new-game, or run the version "
                "the save came from."
                % (saved.get("id") or "?", saved.get("version") or "?", saved_format,
                   current["id"], current["version"], SAVE_FORMAT_VERSION)
            )
            return
        report = world_snapshot.restore(
            self.world,
            record.get("snapshot") or {},
            time_manager=self.time_manager,
            weather_manager=self.weather_manager,
        )
        if not report.clean:
            note = (
                "The saved world named things this version of the content no longer has and they were skipped: "
                "rooms %s, regions %s, NPCs %s."
                % (report.skipped_rooms[:5], report.skipped_regions[:5], report.skipped_npcs[:5])
            )
            Logger.warning("DurableState", note)
            self.persistence_notices.append(note)
        self._last_autosave_at = float(self.world.clock.now())

    # -- keeping it ----------------------------------------------------------------------

    def _autosave_world(self, force: bool = False) -> None:
        if not self.durable_persistence:
            return
        now = float(self.world.clock.now())
        if not force and now - self._last_autosave_at < AUTOSAVE_INTERVAL_SECONDS:
            return
        self._last_autosave_at = now
        snapshot = world_snapshot.capture(
            self.world, time_manager=self.time_manager, weather_manager=self.weather_manager
        )
        self.persistence.queue_world_state(
            WORLD_STATE_KEY,
            {
                "envelope": {
                    "content_set": self._content_identity(),
                    "save_format_version": SAVE_FORMAT_VERSION,
                    "saved_at": time.time(),
                },
                "snapshot": snapshot,
            },
        )

    def _persist_character(self, session_id: str) -> None:
        player = self.get_player_for_session(session_id)
        if not player:
            return
        self.persistence.queue_entity_upsert(
            entity_id="%s:%s" % (CHARACTER_ENTITY_TYPE, _normalized(player.name)),
            entity_type=CHARACTER_ENTITY_TYPE,
            name=player.name,
            components={
                "envelope": {"content_set": self._content_identity(), "save_format_version": SAVE_FORMAT_VERSION},
                "clock_now": float(self.world.clock.now()),
                "player": player.to_dict(self.world),
            },
        )
        self._autosave_world()

    # -- resuming a character ------------------------------------------------------------

    def _resume_or_refuse(self, session: Any, requested_name: str) -> Optional[tuple[bool, str, bool]]:
        """Answer a `char create` when a game is already saved; None when nothing is.

        The saved game belongs to its character. Asking for that character's name
        continues it; asking for another name is refused, with what to do instead.
        """
        if not self.durable_persistence:
            return None
        saved = self.persistence.list_entities(CHARACTER_ENTITY_TYPE)
        if not saved:
            return None
        record = max(saved, key=lambda entity: entity.updated_at)
        if _normalized(record.name) != _normalized(requested_name):
            return True, (
                "This game already belongs to %s. Continue it with: char create %s. "
                "To start a new game, restart the server with --new-game." % (record.name, record.name)
            ), False
        return self._resume_character(session, record)

    def _resume_character(self, session: Any, record: Any) -> tuple[bool, str, bool]:
        from engine.player import Player

        payload = record.components
        try:
            player = Player.from_dict(copy.deepcopy(payload["player"]), self.world)
        except Exception as error:  # a save that cannot be read is reported, never guessed at
            Logger.error("DurableState", "Could not read the saved character '%s': %s" % (record.name, error))
            return True, "The saved character %s could not be read: %s" % (record.name, error), False
        if player is None:
            return True, "The saved character %s could not be read." % record.name, False

        saved_id = player.obj_id
        player.obj_id = session.player_id
        player.world = self.world
        # A resumed character gets the id of the connection that resumed it; whatever
        # was bound to the old id (a companion) is bound to the new one.
        from engine.npcs import companions

        companions.rebind_owner(self.world, saved_id, session.player_id)
        self.world.apply_content_player_defaults(player)
        shift_deadlines(player, float(self.world.clock.now()) - float(payload.get("clock_now", self.world.clock.now())))
        if not self.world.get_room_for_player(player):
            player.current_region_id = player.respawn_region_id
            player.current_room_id = player.respawn_room_id
        self.world.players[session.player_id] = player
        settle = getattr(player, "settle_pending_summons", None)
        if callable(settle):
            settle()
        if self.world.quest_manager:
            self.world.quest_manager.ensure_initial_quests(player)
        session.resumed = True
        return True, "Welcome back, %s." % player.name, True
