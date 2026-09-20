# engine/server/headless/lifecycle.py
"""LifecycleMixin: extracted from HeadlessServer (see headless_server.py) as part
of the P8 file-splitting pass -- a pure move, no behavior change. Composed
back into HeadlessServer alongside the other headless/* mixins.
"""
from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import re

import engine.commands  # noqa: F401 - force command module registration
from engine.commands.command_system import CommandProcessor
from engine.core.clock import Clock, SimulatedClock, WallClock
from engine.core.advancement import AdvancementManager
from engine.core.backgrounds import BackgroundManager
from engine.core.collection_manager import CollectionManager
from engine.core.discovery_manager import DiscoveryManager
from engine.core.knowledge_manager import KnowledgeManager
from engine.core.titles import TitleManager
from engine.core.plugin_manager import PluginManager
from engine.dialogue.manager import DialogueManager
from engine.core.time_manager import TimeManager
from engine.core.weather_manager import WeatherManager
from engine.crafting.crafting_manager import CraftingManager
from engine.server.protocol import build_server_event, validate_client_command_envelope
from engine.server.persistence import SqliteStore
from engine.server.world_effects_heartbeat import WorldEffectsHeartbeat
from engine.server.feature_profile import FeatureProfile
from engine.server.entitlement import EntitlementGuard
from engine.server.content_set import ContentSetDefinition, load_content_set
from engine.server.system_providers import (
    BuiltinWeatherProvider,
    BuiltinWorldEffectsProvider,
    CustomWeatherProvider,
    CustomWorldEffectsProvider,
    DisabledWeatherProvider,
    DisabledWorldEffectsProvider,
)
from engine.world.world import World
from engine.world.region import Region
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import initialize_npc_schedules
from engine.utils.utils import _serialize_item_reference

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.server.headless_server import HeadlessServer
    from engine.server.headless.models import Session, Party


class LifecycleMixin:
    def broadcast_to_room(self, region_id: str, room_id: str, message: str, exclude_session_id: Optional[str] = None) -> None:
        if not hasattr(self, "pending_broadcasts"): self.pending_broadcasts = []
        for session_id, session in self.sessions.items():
            if session_id == exclude_session_id: continue
            player = self.get_player_for_session(session_id)
            if player and player.current_region_id == region_id and player.current_room_id == room_id:
                self.pending_broadcasts.append(self._event("text", session_id, message))

    def broadcast_global(self, message: str, exclude_session_id: Optional[str] = None) -> None:
        if not hasattr(self, "pending_broadcasts"): self.pending_broadcasts = []
        for session_id in self.sessions.keys():
            if session_id == exclude_session_id: continue
            self.pending_broadcasts.append(self._event("text", session_id, message))

    def shutdown(self) -> None:
        # Persist all active player sessions before shutdown
        for session_id in list(self.sessions.keys()):
            self.persist_player_snapshot(session_id)
        self._persist_global_player_snapshot()
        self.persistence.flush()
        self.persistence.stop_async_writer()
        self.persistence.close()

    def persist_player_snapshot(self, session_id: str) -> None:
        player = self.get_player_for_session(session_id)
        if not player:
            return
        components = player.to_dict(self.world)
        self.persistence.queue_entity_upsert(
            entity_id=player.obj_id,
            entity_type="player",
            name=player.name,
            components=components,
        )

    def _persist_global_player_snapshot(self) -> None:
        player = getattr(self.world, "player", None)
        if not player:
            return
        components = player.to_dict(self.world)
        self.persistence.queue_entity_upsert(
            entity_id=player.obj_id,
            entity_type="player",
            name=player.name,
            components=components,
        )

    def discard_background_batch(self) -> None:
        """Drop accumulated background events when nobody is subscribed.

        The world advances whether or not anyone is connected, and most of what a
        tick produces is addressed to whoever happens to be in the room: a season
        change, an NPC moving, a field cell spreading. With no sessions those
        events have no recipient, so they are dropped rather than queued.

        Dropping is right here, and not a silent loss of state: the underlying
        change has already happened in the world (and, for field cells, been
        queued for persistence). What is discarded is the *notification*, which is
        reconstruction-free -- the next session to arrive gets the current state
        from the world itself, not from a backlog of stale deltas.
        """
        self._background_event_batch.clear()

    def _flush_background_batch(self, session_id: str) -> List[Dict[str, Any]]:
        """Drain accumulated background events, optionally coalescing text payloads."""
        if not self._background_event_batch:
            return []
        if not self._background_batch_enabled:
            out = list(self._background_event_batch)
            self._background_event_batch.clear()
            return out        # Coalesce consecutive text events for the same session into one payload
        # to reduce round-trips on mobile / high-latency links.
        coalesced: List[Dict[str, Any]] = []
        text_lines: List[str] = []
        for ev in self._background_event_batch:
            if ev.get("type") == "text" and ev.get("session_id") == session_id:
                text_lines.append(str(ev.get("payload", "")))
            else:
                if text_lines:
                    coalesced.append(self._event("text", session_id, "\n".join(text_lines)))
                    text_lines = []
                coalesced.append(ev)
        if text_lines:
            coalesced.append(self._event("text", session_id, "\n".join(text_lines)))
        self._background_event_batch.clear()
        return coalesced

    def tick(self, session_id: Optional[str] = None, dt: Optional[float] = None) -> List[Dict[str, Any]]:
        """Advance the shared world by `dt` seconds.

        `session_id` names the session whose player should also be advanced, and
        may be None: the world is not a property of who is connected. Time of day,
        seasons, weather, NPC and region activity, and field propagation all move
        on a server with nobody logged in, which is what makes a persistent world
        persistent. Only the player-specific work at the end needs a session.

        Returns the events addressed to `session_id` directly. Ambient and
        world-state events go to the background batch; with no session there is
        nothing to flush them to, and the caller discards them.
        """
        self._sync_providers_with_profile()
        if not self._world_mode_tick_enabled():
            return []
        if dt is None or self.deterministic_test_mode:
            dt = self.tick_dt
        # Advances the same shared clock that gameplay timers (combat/spell
        # cooldowns, respawns, jail sentences, DOT ticks) read via
        # world.clock.now() -- a no-op under WallClock (real time already
        # passes on its own), and the sole thing that makes those timers
        # move under SimulatedClock, in lockstep with this tick's dt.
        self.world.clock.advance(dt)

        events: List[Dict[str, Any]] = []
        time_change = self.time_manager.update(dt)
        if time_change:
            old_period, new_period = time_change
            season = self.time_manager.time_data.get("season", "summer")
            self.weather_provider.on_time_period_change(self, season)
            msg = self.time_manager.get_time_transition_message(old_period, new_period)
            if msg:
                # Time-of-day transitions are background ambient — batch them.
                self._background_event_batch.append(self._event("text", session_id, msg))

        for location, msg in self.world.update():
            if self._is_combat_adjacent_message(msg):
                continue
            # World NPC/region tick messages are background — batch, but route
            # each one only to sessions whose player is actually in the room
            # it happened in. Without this, whichever session's poll happens
            # to trigger the periodic world tick would receive combat/ambient
            # text for events happening anywhere else in the world.
            if location is None:
                self._background_event_batch.append(self._event("text", session_id, msg))
                continue
            region_id, room_id = location
            for other_session_id in self.sessions:
                other_player = self.get_player_for_session(other_session_id)
                if (
                    other_player
                    and other_player.current_region_id == region_id
                    and other_player.current_room_id == room_id
                ):
                    self._background_event_batch.append(self._event("text", other_session_id, msg))

        player = self.get_player_for_session(session_id)
        if player and player.is_alive:
            for msg in player.update(self.world.clock.now(), dt):
                if self._is_combat_adjacent_message(msg):
                    continue
                # Player regen/effect messages are player-facing — emit direct.
                events.append(self._event("text", session_id, msg))

        # World-effects tick (blight, fields): background — batch.
        for ev in self.world_effects_provider.tick(self, session_id):
            self._background_event_batch.append(ev)

        return events
