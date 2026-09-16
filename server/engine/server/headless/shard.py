# engine/server/headless/shard.py
"""ShardMixin: extracted from HeadlessServer (see headless_server.py) as part
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


class ShardMixin:
    def shard_policy_value(self, key: str, default: Any = None) -> Any:
        raw = getattr(self.feature_profile, "raw", {})
        if not isinstance(raw, dict):
            return default
        for node_name in ("persistent_shard", "shard"):
            node = raw.get(node_name, {})
            if isinstance(node, dict) and key in node:
                return node.get(key, default)
        return default

    def shard_session_resume_policy(self) -> str:
        return str(self.shard_policy_value("session_resume_policy", "enabled")).strip().lower() or "enabled"

    def shard_late_join_policy(self) -> str:
        return str(self.shard_policy_value("late_join_policy", "enabled")).strip().lower() or "enabled"

    def shard_disconnect_timeout_policy(self) -> str:
        return str(self.shard_policy_value("disconnect_timeout_policy", "indefinite")).strip().lower() or "indefinite"

    def shard_disconnect_grace_window_seconds(self) -> float:
        raw_value = self.shard_policy_value("disconnect_timeout_seconds", 300)
        try:
            return max(0.0, float(raw_value))
        except (TypeError, ValueError):
            return 300.0

    def _resolve_initial_shard_runtime_state(self) -> str:
        raw_value = self.shard_policy_value("initial_runtime_state", "normal")
        state = str(raw_value).strip().lower() or "normal"
        if state not in {"normal", "drain", "freeze", "maintenance"}:
            return "normal"
        return state

    def _resolve_initial_shard_runtime_message(self) -> str:
        return str(self.shard_policy_value("initial_runtime_message", "")).strip()

    def shard_runtime_state(self) -> str:
        state = str(self._shard_runtime_state).strip().lower() or "normal"
        if state not in {"normal", "drain", "freeze", "maintenance"}:
            return "normal"
        return state

    def shard_runtime_message(self) -> str:
        return str(self._shard_runtime_message).strip()

    def set_shard_runtime_state(
        self,
        state: str,
        message: str = "",
        *,
        changed_by_session_id: str = "",
    ) -> tuple[bool, str]:
        normalized_state = str(state).strip().lower()
        if normalized_state not in {"normal", "drain", "freeze", "maintenance"}:
            return False, "Unknown shard mode. Use: normal, drain, freeze, or maintenance."
        self._shard_runtime_state = normalized_state
        self._shard_runtime_message = str(message).strip()
        self._shard_last_mode_change_at = time.time()
        self._shard_last_mode_changed_by_session_id = str(changed_by_session_id).strip()
        if self._shard_runtime_message:
            return True, f"Shard mode set to {normalized_state}: {self._shard_runtime_message}"
        return True, f"Shard mode set to {normalized_state}."

    def build_shard_runtime_payload(self) -> Dict[str, Any]:
        state = self.shard_runtime_state()
        message = self.shard_runtime_message()
        tick_enabled = state not in {"freeze", "maintenance"}
        gameplay_enabled = state not in {"freeze", "maintenance"}
        character_creation_enabled = state == "normal"
        if state == "drain":
            character_creation_enabled = False
        return {
            "state": state,
            "message": message,
            "tick_enabled": tick_enabled,
            "gameplay_enabled": gameplay_enabled,
            "character_creation_enabled": character_creation_enabled,
        }

    def shard_new_session_admission_block_reason(self) -> str:
        if self.feature_profile.resolved_world_mode() != "persistent_shard":
            return ""

        state = self.shard_runtime_state()
        message = self.shard_runtime_message()
        suffix = f" {message}" if message else ""
        if state == "drain":
            return f"New players cannot join while the shard is draining.{suffix}".strip()
        if state == "freeze":
            return f"New players cannot join while the shard is frozen.{suffix}".strip()
        if state == "maintenance":
            return f"New players cannot join during shard maintenance.{suffix}".strip()

        late_join_policy = self.shard_late_join_policy()
        if late_join_policy in {"disabled", "off", "forbidden", "closed"}:
            if len(self.world.players) > 0:
                return "New players cannot join this shard after it has started."
        return ""

    def build_shard_diagnostics_payload(self, now: float | None = None) -> Dict[str, Any]:
        current_time = time.time() if now is None else float(now)
        connected_sessions = 0
        disconnected_sessions = 0
        resumable_sessions = 0
        expired_grace_window_sessions = 0
        max_disconnected_age_seconds = 0.0
        for session in self.sessions.values():
            if getattr(session, "connected", False):
                connected_sessions += 1
                continue
            disconnected_sessions += 1
            disconnected_at = getattr(session, "disconnected_at", None)
            if disconnected_at is not None:
                resumable_sessions += 1
                age_seconds = max(0.0, current_time - float(disconnected_at))
                max_disconnected_age_seconds = max(max_disconnected_age_seconds, age_seconds)
            if self._shard_resume_window_expired(session, now=current_time):
                expired_grace_window_sessions += 1

        grace_window_seconds = self.shard_disconnect_grace_window_seconds()
        return {
            "world_mode": self.feature_profile.resolved_world_mode(),
            "runtime_state": self.shard_runtime_state(),
            "runtime_message": self.shard_runtime_message(),
            "late_join_policy": self.shard_late_join_policy(),
            "new_session_admission_enabled": self.shard_new_session_admission_block_reason() == "",
            "new_session_admission_reason": self.shard_new_session_admission_block_reason(),
            "total_session_count": len(self.sessions),
            "connected_session_count": connected_sessions,
            "disconnected_session_count": disconnected_sessions,
            "resumable_session_count": resumable_sessions,
            "expired_grace_window_session_count": expired_grace_window_sessions,
            "grace_window_seconds": float(grace_window_seconds),
            "max_disconnected_age_seconds": float(round(max_disconnected_age_seconds, 3)),
            "last_mode_change_at": self._shard_last_mode_change_at,
            "last_mode_changed_by_session_id": str(self._shard_last_mode_changed_by_session_id),
        }

    def shard_character_creation_block_reason(self) -> str:
        if self.feature_profile.resolved_world_mode() != "persistent_shard":
            return ""
        runtime = self.build_shard_runtime_payload()
        if bool(runtime.get("character_creation_enabled", True)):
            return ""
        state = str(runtime.get("state", "normal"))
        message = str(runtime.get("message", "")).strip()
        suffix = f" {message}" if message else ""
        if state == "drain":
            return f"Character creation is temporarily disabled while the shard is draining.{suffix}".strip()
        if state == "freeze":
            return f"Character creation is temporarily disabled while the shard is frozen.{suffix}".strip()
        if state == "maintenance":
            return f"Character creation is temporarily disabled during shard maintenance.{suffix}".strip()
        return ""

    def shard_gameplay_block_reason(self) -> str:
        if self.feature_profile.resolved_world_mode() != "persistent_shard":
            return ""
        runtime = self.build_shard_runtime_payload()
        if bool(runtime.get("gameplay_enabled", True)):
            return ""
        state = str(runtime.get("state", "normal"))
        message = str(runtime.get("message", "")).strip()
        suffix = f" {message}" if message else ""
        if state == "freeze":
            return f"Gameplay is temporarily frozen for this shard.{suffix}".strip()
        if state == "maintenance":
            return f"Gameplay is temporarily unavailable during shard maintenance.{suffix}".strip()
        return ""

    def _shard_resume_window_expired(self, session: Session, now: float | None = None) -> bool:
        disconnected_at = getattr(session, "disconnected_at", None)
        if disconnected_at is None:
            return False
        current_time = time.time() if now is None else float(now)
        return (current_time - float(disconnected_at)) > self.shard_disconnect_grace_window_seconds()

    def prune_expired_shard_sessions(self, now: float | None = None) -> List[Dict[str, Any]]:
        if self.feature_profile.resolved_world_mode() != "persistent_shard":
            return []
        if self.shard_disconnect_timeout_policy() != "grace_window":
            return []

        impacted_player_ids: set[str] = set()
        removed_any = False
        for session_id, session in list(self.sessions.items()):
            if getattr(session, "connected", False):
                continue
            if not self._shard_resume_window_expired(session, now=now):
                continue
            impacted_player_ids.update(self._party_impacted_player_ids(str(session.player_id)))
            self.persist_player_snapshot(session_id)
            self.sessions.pop(session_id, None)
            removed_any = True

        if not removed_any:
            return []
        return self._party_sync_events_for_player_ids(list(sorted(impacted_player_ids)))
