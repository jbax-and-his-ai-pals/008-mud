# engine/server/headless/session.py
"""SessionMixin: extracted from HeadlessServer (see headless_server.py) as part
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
from engine.config import DEFAULT_PLAYER_CLASS_NAME
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
from engine.server.headless.models import Session  # constructed at runtime below

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from engine.server.headless_server import HeadlessServer
    from engine.server.headless.models import Party


class SessionMixin:
    def create_session(
        self,
        player_id: Optional[str] = None,
        entitlements: Optional[List[str]] = None,
        presentation_mode: Optional[str] = None,
    ) -> Session:
        session_id = uuid.uuid4().hex
        resolved_player_id = str(player_id or "").strip()
        if resolved_player_id == "":
            resolved_player_id = f"session_{session_id[:8]}" if self.require_character_creation else "player"
        granted = self.entitlement_guard.apply_defaults(list(entitlements or []))
        session = Session(session_id=session_id, player_id=resolved_player_id)
        session.entitlements = granted
        resolved_mode = str(presentation_mode or self.default_presentation_mode).strip().lower()
        session.presentation_mode = resolved_mode if resolved_mode in {"player", "test"} else "player"
        self.sessions[session_id] = session
        if self.feature_profile.resolved_world_mode() == "single_player_story" and self._story_primary_session_id is None:
            self._story_primary_session_id = session_id
        
        return session

    def _world_mode_command_blocked(self, session_id: str) -> tuple[bool, str]:
        mode = self.feature_profile.resolved_world_mode()
        if mode not in {"single_player_story", "finite_adventure"}:
            return False, ""
        if self._story_primary_session_id is None:
            self._story_primary_session_id = session_id
            return False, ""
        if session_id == self._story_primary_session_id:
            return False, ""
        return True, f"Server world mode '{mode}' allows only the primary session to issue gameplay commands."

    def _world_mode_tick_enabled(self) -> bool:
        mode = self.feature_profile.resolved_world_mode()
        # Archive worlds are intentionally static snapshots.
        if mode == "readonly_archive":
            return False
        if mode == "persistent_shard" and self.shard_runtime_state() in {"freeze", "maintenance"}:
            return False
        return True

    def validate_resume_session_target(self, requested_session_id: str) -> tuple[bool, str]:
        requested = str(requested_session_id).strip()
        if requested == "" or requested not in self.sessions:
            return False, "Resume rejected: unknown session_id"

        mode = self.feature_profile.resolved_world_mode()
        session = self.sessions.get(requested)
        if mode == "persistent_shard":
            resume_policy = self.shard_session_resume_policy()
            if resume_policy in {"disabled", "forbidden", "off"}:
                return False, "Resume rejected: persistent_shard session resume is disabled by server policy."
            timeout_policy = self.shard_disconnect_timeout_policy()
            if (
                timeout_policy == "grace_window"
                and session is not None
                and not getattr(session, "connected", False)
                and self._shard_resume_window_expired(session)
            ):
                return False, "Resume rejected: persistent_shard disconnect grace window has expired."

        if mode not in {"single_player_story", "finite_adventure"}:
            return True, ""

        primary = self._story_primary_session_id
        if primary and primary not in self.sessions:
            primary = None
            self._story_primary_session_id = None
        if primary is None:
            self._story_primary_session_id = requested
            return True, ""
        if requested != primary:
            return False, f"Resume rejected: {mode} allows resuming only the primary session."
        return True, ""

    def get_player_for_session(self, session_id: str) -> Any:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return self.world.players.get(session.player_id)

    def _handle_character_creation_command(self, session_id: str, text: str) -> tuple[bool, str, bool]:
        normalized = str(text).strip()
        lowered = normalized.lower()
        if lowered in {"help", "?", "char help", "character help"}:
            return True, (
                "Create your character with: char create <name>\n"
                "Choose where you begin with: char create <name> as <background>\n"
                "Type 'backgrounds' to see the options."
            ), False

        prefix = None
        if lowered.startswith("char create "):
            prefix = "char create "
        elif lowered.startswith("character create "):
            prefix = "character create "
        if prefix is None:
            return False, "", False

        raw_name = normalized[len(prefix):].strip()

        # Optional "as <background>". A background decides where you begin --
        # stats, kit, a couple of skills -- and locks nothing, so omitting it is
        # perfectly valid and gets the content set's default.
        background_query = ""
        if " as " in raw_name.lower():
            split_index = raw_name.lower().rindex(" as ")
            background_query = raw_name[split_index + 4:].strip()
            raw_name = raw_name[:split_index].strip()

        if len(raw_name) < 3 or len(raw_name) > 24:
            return True, "Character name must be 3-24 characters.", False
        if not re.fullmatch(r"[A-Za-z0-9 _'\-]+", raw_name):
            return True, "Character name contains unsupported characters.", False

        background = None
        if background_query:
            background = self.background_manager.resolve(background_query)
            if background is None:
                names = ", ".join(b.name for b in self.background_manager.available()) or "none defined"
                return True, (
                    "There is no background called '%s'. Available: %s."
                    % (background_query, names)
                ), False
        else:
            # A content set that declares no backgrounds has no starting kit of
            # its own, and the ruleset's `player_defaults` are that kit. The
            # placeholder background exists so a creation screen has a label to
            # show; treating it as "a background was applied" suppressed those
            # defaults, handing the character an empty pack and no abilities.
            background = (
                self.background_manager.default_background()
                if self.background_manager.available()
                else None
            )

        session = self.sessions.get(session_id)
        if session is None:
            return True, "Unknown session.", False
        shard_block_reason = self.shard_character_creation_block_reason()
        if shard_block_reason:
            return True, shard_block_reason, False
        shard_admission_reason = self.shard_new_session_admission_block_reason()
        if shard_admission_reason:
            return True, shard_admission_reason, False
        if session.player_id in self.world.players:
            return True, "Character already exists for this session.", False

        from engine.player import Player
        new_player = Player(raw_name, world=self.world)
        new_player.obj_id = session.player_id
        new_player.world = self.world
        self.world.initialize_content_player(new_player)
        # Applied after content defaults so a background's stats and kit are
        # not overwritten by them.
        background_applied = background is not None and background.background_id
        if background_applied and new_player.runtime_state.magic is not None:
            # Start from nothing so the background's spell list is the whole
            # list. Without this the ruleset's generic defaults stayed and every
            # background inherited them.
            new_player.runtime_state.magic.known_spells = set()
        self.background_manager.apply(new_player, background)

        # A background owns the *whole* starting kit -- stats, gear, spells,
        # skills, recipes. The ruleset's generic `player_defaults.starting_inventory`
        # and default spell list stay as the fallback for a content set that
        # defines no backgrounds, but are not granted on top of one; doing both
        # gave every character two foraging knives and two healing potions, each
        # from a different system.
        if not background_applied:
            from engine.world.definition_loader import grant_starting_inventory
            grant_starting_inventory(self.world, new_player, self.world.bootstrap_starter_items)
        start_region = str(getattr(self.world, "bootstrap_start_region", "") or self.content_set.start_region_id)
        start_room = str(getattr(self.world, "bootstrap_start_room", "") or self.content_set.start_room_id)
        new_player.current_region_id = start_region
        new_player.current_room_id = start_room
        new_player.respawn_region_id = start_region
        new_player.respawn_room_id = start_room
        self.world.players[session.player_id] = new_player
        if self.world.quest_manager:
            # World bootstrap seeds the board with initial_player=None (no
            # character exists yet at that point), so ensure_initial_quests()
            # bails out immediately and the board is left permanently empty.
            # The first character to ever exist gives it a real player to
            # scale quests against.
            self.world.quest_manager.ensure_initial_quests(new_player)

        # Record the starting region, so "where have I been" is true from the
        # first moment rather than only after the first walk -- but seed it
        # silently. Waking up in the town you spawned in is not a discovery, and
        # paying the region grant for it put every new character at 90/100 XP
        # for their first level before they had done anything.
        self.advancement_manager.ingest_legacy_discoveries(new_player)
        self.advancement_manager.seed(new_player, "region", start_region)
        # A set that declares no backgrounds has no background name to show; the
        # character's own class label is what it starts as.
        role = background.name if background is not None else (
            getattr(getattr(new_player.runtime_state, "progression", None), "player_class", "")
            or DEFAULT_PLAYER_CLASS_NAME
        )
        return True, f"Character created: {raw_name} ({role})", True

    def build_opening_guidance(self) -> str:
        """Format the selected content set's optional first-session brief."""
        opening = getattr(self.content_set, "opening", {}) if self.content_set else {}
        if not isinstance(opening, dict):
            return ""
        heading = str(opening.get("heading", "")).strip()
        intro = str(opening.get("intro", "")).strip()
        objectives = opening.get("objectives", [])
        objectives_heading = str(opening.get("objectives_heading", "First steps:")).strip() or "First steps:"
        lines = [value for value in (heading, intro) if value]
        if isinstance(objectives, list) and objectives:
            steps = []
            for objective in objectives:
                if not isinstance(objective, dict):
                    continue
                instruction = str(objective.get("instruction", "")).strip()
                command = str(objective.get("command", "")).strip()
                if instruction:
                    command_suffix = f" ({command})" if command else ""
                    steps.append(f"{instruction}{command_suffix}")
            if steps:
                lines.append(objectives_heading + "\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1)))
        return "\n\n".join(lines)

    def _display_name_for_player_id(self, player_id: str) -> str:
        player = self.world.players.get(player_id)
        if player is not None:
            return str(getattr(player, "name", player_id))
        for session in self.sessions.values():
            if session.player_id == player_id:
                return str(session.player_id)
        return str(player_id)

    def _find_online_session_by_player_id(self, player_id: str) -> Session | None:
        for session in self.sessions.values():
            if not getattr(session, "connected", False):
                continue
            if str(session.player_id) == str(player_id):
                return session
        return None

    def mark_session_connected(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is not None:
            session.connected = True
            session.disconnected_at = None

    def mark_session_disconnected(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if session is not None:
            session.connected = False
            session.disconnected_at = time.time()

    def _find_player_id_by_name(self, name: str) -> tuple[str, str]:
        normalized = str(name).strip().lower()
        if normalized == "":
            return "", "Missing player name."
        matches: List[str] = []
        for player_id, player in self.world.players.items():
            player_name = str(getattr(player, "name", "")).strip().lower()
            if player_name == normalized or str(player_id).strip().lower() == normalized:
                matches.append(str(player_id))
        unique_matches = sorted(set(matches))
        if not unique_matches:
            return "", f"No player found matching '{name}'."
        if len(unique_matches) > 1:
            return "", f"Multiple players match '{name}'. Use a more specific name."
        return unique_matches[0], ""
