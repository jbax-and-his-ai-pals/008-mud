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
from engine.core.collection_manager import CollectionManager
from engine.core.knowledge_manager import KnowledgeManager
from engine.core.plugin_manager import PluginManager
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
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import initialize_npc_schedules
from engine.utils.utils import _serialize_item_reference


class _NullRenderer:
    def __init__(self) -> None:
        self.messages: List[str] = []
        self.text_buffer: List[str] = []
        self.scroll_offset = 0

    def add_message(self, message: str) -> None:
        self.messages.append(message)
        self.text_buffer.append(message)

    def add_floating_text(self, _text: str, _x: int, _y: int, _color: tuple[int, int, int]) -> None:
        return


class _NullInputHandler:
    def __init__(self) -> None:
        self.input_text = ""
        self.command_history: List[str] = []
        self.history_index = -1


@dataclass
class Session:
    session_id: str
    player_id: str
    capabilities: List[str] = field(default_factory=list)
    entitlements: List[str] = field(default_factory=list)
    connected: bool = False
    disconnected_at: float | None = None


@dataclass
class Party:
    party_id: str
    leader_player_id: str
    member_player_ids: List[str] = field(default_factory=list)


class HeadlessServer:
    """Minimal authoritative headless runtime that reuses existing world/command systems."""

    def __init__(
        self,
        save_file: str = "server_save.json",
        db_path: Optional[str] = None,
        data_root: Optional[str] = None,
        content_set_path: Optional[str] = None,
        field_config_path: Optional[str] = None,
        feature_profile_path: Optional[str] = None,
        starter_items: Optional[List[Dict[str, Any] | str]] = None,
        entitlement_policy: Optional[Dict[str, Any]] = None,
        mods_dir: Optional[str] = None,
        tick_rate_hz: float = 10.0,
        deterministic_test_mode: bool = False,
        require_character_creation: bool = True,
        boot_warning_fail_codes: Optional[List[str]] = None,
    ) -> None:
        self.tick_rate_hz = tick_rate_hz
        self.tick_dt = 1.0 / self.tick_rate_hz
        self.deterministic_test_mode = deterministic_test_mode
        if self.deterministic_test_mode:
            import random
            random.seed(42)
        if not content_set_path:
            raise ValueError("A content_set_path is required. The runtime has no default world.")
        definition, content_set_issues = load_content_set(Path(content_set_path))
        errors = [issue.message for issue in content_set_issues if issue.severity == "error"]
        if definition is None or errors:
            detail = "; ".join(errors) if errors else "unknown validation error"
            raise ValueError(f"Invalid content set '{content_set_path}': {detail}")
        selected_data_root = os.path.abspath(str(definition.data_root))
        if data_root and os.path.abspath(data_root) != selected_data_root:
            raise ValueError(
                "data_root conflicts with selected content set: "
                f"{os.path.abspath(data_root)} != {selected_data_root}"
            )
        self.content_set: ContentSetDefinition = definition
        self.content_set_path: str = str(definition.manifest_path)
        data_root = selected_data_root

        self.data_root = os.path.abspath(data_root) if data_root else None
        self.world = World(data_root=self.data_root, content_set=self.content_set)
        setattr(self.world, "server", self)
        self.world.bootstrap_starter_items = list(starter_items) if starter_items else None
        self.command_processor = CommandProcessor()
        # Client-side display hint (text/icon/hybrid); the server does not
        # render, but `invmode` reads/writes it for parity with GameManager.
        self.inventory_mode = "hybrid"
        self.time_manager = TimeManager()
        self.weather_manager = WeatherManager()
        self.crafting_manager = (
            CraftingManager(self.world, data_root=self.world.data_root)
            if self.world.has_capability("crafting")
            else None
        )
        self.boot_warnings: List[str] = []
        self.boot_warning_records: List[Dict[str, str]] = []
        self._boot_warning_keys: set[tuple[str, str, str]] = set()
        self.knowledge_manager = KnowledgeManager(
            self.world,
            warning_sink=self.add_boot_warning,
            data_root=self.world.data_root,
        )
        self.collection_manager = CollectionManager(self.world, data_root=self.world.data_root)
        self.renderer = _NullRenderer()
        self.input_handler = _NullInputHandler()
        self.current_save_file = save_file
        self.db_path = db_path or os.path.abspath("server_state.sqlite3")
        self.persistence = SqliteStore(self.db_path)
        self.persistence.start_async_writer()
        self.feature_profile = FeatureProfile.load(feature_profile_path)
        self._seed_boot_warnings_from_profile()
        self.entitlement_guard = EntitlementGuard(entitlement_policy or {})
        self.mods_dir = mods_dir or os.path.abspath("mods")
        # Server contract: players are created explicitly by client flow.
        # Auto-spawned session players are not supported.
        self.require_character_creation = require_character_creation
        self.boot_warning_fail_codes = {
            str(code).strip() for code in list(boot_warning_fail_codes or []) if str(code).strip()
        }
        self.custom_weather_providers: Dict[str, Any] = {}
        self.custom_world_effects_providers: Dict[str, Any] = {}
        self.fields: Dict[str, WorldEffectsHeartbeat] = {}
        self.field_polarities: Dict[str, str] = {}
        self.field_interaction_rules: Dict[str, Dict[str, float]] = {
            # source_field -> {target_field: suppression_coefficient}
            "sanctity": {"blight": 0.60},
            "harmony": {"entropy": 0.45},
        }
        self.field_interaction_profiles: Dict[str, Dict[str, float]] = {
            "positive_suppresses_negative": {"coefficient": 0.60}
        }
        default_field_config = (
            os.path.join(self.data_root, "world", "field_interactions.json")
            if self.data_root
            else os.path.abspath(os.path.join("data", "world", "field_interactions.json"))
        )
        self.field_config_path = field_config_path or default_field_config
        self._load_field_interaction_config()
        # Providers are initialized to safe built-in defaults here.  Proper
        # resolution — including custom/disabled modes and plugin-registered
        # providers — is deferred to _sync_providers_with_profile() below,
        # which runs after the plugin manager has loaded all mods.  This
        # avoids spurious "provider not found" warnings for providers that are
        # supplied by plugins (e.g. social_no_combat → sample.effects.balance).
        self.weather_provider = BuiltinWeatherProvider()
        self.world_effects_provider = BuiltinWorldEffectsProvider()
        self.default_field_id = "blight"
        self.default_field_polarity = "negative"
        self.game_state = "playing"
        self.debug_mode = False
        self.debug_ignore_player = False
        self.ui_manager = None
        self.is_auto_traveling = False
        self._story_primary_session_id: str | None = None
        self._shard_runtime_state = self._resolve_initial_shard_runtime_state()
        self._shard_runtime_message = self._resolve_initial_shard_runtime_message()
        self._shard_last_mode_change_at: float | None = None
        self._shard_last_mode_changed_by_session_id: str = ""
        self.parties: Dict[str, Party] = {}
        self.player_party_membership: Dict[str, str] = {}
        self.pending_party_invites: Dict[str, str] = {}
        self.party_loot_cursors: Dict[str, int] = {}

        self.world.game = self
        self.world.skip_initial_player = True
        self.world.initialize_new_world(
            start_region=self.content_set.start_region_id,
            start_room=self.content_set.start_room_id,
        )
        self._seed_definition_load_warnings()
        self.time_manager.initialize_time()
        self.sessions: Dict[str, Session] = {}
        self.pending_broadcasts: List[Dict[str, Any]] = []
        # M3: background event batch — world/weather/effects messages are
        # accumulated here and flushed once per command cycle so mobile clients
        # receive one coalesced payload instead of N individual frames.
        self._background_event_batch: List[Dict[str, Any]] = []
        self._background_batch_enabled: bool = True
        self._init_field_state()
        self._persist_global_player_snapshot()
        self.plugin_manager = PluginManager(self, mods_dir=self.mods_dir)
        if self.feature_profile.mods_mode == "enabled":
            self.plugin_manager.load_all_plugins()
        else:
            self.add_boot_warning(
                code="profile.mods.disabled",
                message="Mods are disabled by server profile.",
                source="profile",
            )
        # Resolve actual providers now that plugins have registered theirs.
        self._sync_providers_with_profile()
        self._enforce_boot_warning_policy()

    def _seed_boot_warnings_from_profile(self) -> None:
        warnings = list(getattr(self.feature_profile, "warnings", []))
        for warning in warnings:
            self.add_boot_warning(
                code="profile.mode.invalid",
                message=str(warning),
                source="profile",
            )

    def _seed_definition_load_warnings(self) -> None:
        stats = getattr(self.world, "definition_load_stats", {})
        if not isinstance(stats, dict):
            return
        spell_stats = stats.get("spell_registry", {})
        if isinstance(spell_stats, dict):
            overwrite_count = int(spell_stats.get("overwrites", 0))
            spell_file_errors = int(spell_stats.get("file_errors", 0))
            spell_dir_missing = int(spell_stats.get("dir_missing", 0))
            if overwrite_count > 0:
                self.add_boot_warning(
                    code="content.spells.duplicate_ids",
                    message=f"Spell registry loaded with {overwrite_count} duplicate spell definition override(s).",
                    source="content",
                )
            if spell_file_errors > 0:
                self.add_boot_warning(
                    code="content.spells.file_errors",
                    message=f"Spell registry encountered {spell_file_errors} file load/decode error(s).",
                    source="content",
                )
            if spell_dir_missing > 0:
                self.add_boot_warning(
                    code="content.spells.dir_missing",
                    message="Magic definitions directory is missing for current data root.",
                    source="content",
                )

        item_stats = stats.get("item_templates", {})
        if isinstance(item_stats, dict):
            item_dups = int(item_stats.get("duplicate_ids", 0))
            item_invalid = int(item_stats.get("invalid_missing_required", 0))
            item_errors = int(item_stats.get("file_errors", 0))
            item_dir_missing = int(item_stats.get("dir_missing", 0))
            if item_dups > 0:
                self.add_boot_warning(
                    code="content.items.duplicate_ids",
                    message=f"Item templates detected {item_dups} duplicate ID collision(s).",
                    source="content",
                )
            if item_invalid > 0:
                self.add_boot_warning(
                    code="content.items.invalid_missing_required",
                    message=f"Item templates skipped {item_invalid} invalid record(s) missing required fields.",
                    source="content",
                )
            if item_errors > 0:
                self.add_boot_warning(
                    code="content.items.file_errors",
                    message=f"Item templates encountered {item_errors} file load error(s).",
                    source="content",
                )
            if item_dir_missing > 0:
                self.add_boot_warning(
                    code="content.items.dir_missing",
                    message="Item templates directory is missing for current data root.",
                    source="content",
                )

        npc_stats = stats.get("npc_templates", {})
        if isinstance(npc_stats, dict):
            npc_dups = int(npc_stats.get("duplicate_ids", 0))
            npc_invalid = int(npc_stats.get("invalid_missing_name", 0))
            npc_errors = int(npc_stats.get("file_errors", 0))
            npc_dir_missing = int(npc_stats.get("dir_missing", 0))
            if npc_dups > 0:
                self.add_boot_warning(
                    code="content.npcs.duplicate_ids",
                    message=f"NPC templates detected {npc_dups} duplicate ID collision(s).",
                    source="content",
                )
            if npc_invalid > 0:
                self.add_boot_warning(
                    code="content.npcs.invalid_missing_name",
                    message=f"NPC templates skipped {npc_invalid} invalid record(s) missing required name.",
                    source="content",
                )
            if npc_errors > 0:
                self.add_boot_warning(
                    code="content.npcs.file_errors",
                    message=f"NPC templates encountered {npc_errors} file load error(s).",
                    source="content",
                )
            if npc_dir_missing > 0:
                self.add_boot_warning(
                    code="content.npcs.dir_missing",
                    message="NPC templates directory is missing for current data root.",
                    source="content",
                )

    def add_boot_warning(self, code: str, message: str, source: str = "server") -> None:
        normalized_code = str(code).strip() or "server.unknown"
        normalized_message = str(message).strip()
        normalized_source = str(source).strip() or "server"
        key = (normalized_code, normalized_message, normalized_source)
        if key in self._boot_warning_keys:
            return
        self._boot_warning_keys.add(key)
        self.boot_warning_records.append(
            {
                "code": normalized_code,
                "severity": "warning",
                "source": normalized_source,
                "message": normalized_message,
            }
        )
        self.boot_warnings.append(normalized_message)

    def reset_boot_warnings_for_profile(self, profile: FeatureProfile) -> None:
        self.boot_warnings = []
        self.boot_warning_records = []
        self._boot_warning_keys = set()
        self.feature_profile = profile
        self._seed_boot_warnings_from_profile()

    def _enforce_boot_warning_policy(self) -> None:
        if not self.boot_warning_fail_codes:
            return
        present = {
            str(entry.get("code", "")).strip()
            for entry in self.boot_warning_records
            if str(entry.get("code", "")).strip()
        }
        violating = sorted(code for code in present if code in self.boot_warning_fail_codes)
        if violating:
            raise RuntimeError(
                "Boot aborted by warning policy. Disallowed warning code(s): %s"
                % ", ".join(violating)
            )

    def _event(self, event_type: str, session_id: str, payload: Any) -> Dict[str, Any]:
        return build_server_event(event_type, session_id, payload, time.time())

    def _load_field_interaction_config(self) -> None:
        if not self.field_config_path or not os.path.exists(self.field_config_path):
            return
        try:
            with open(self.field_config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return

        if not isinstance(raw, dict):
            return

        loaded_rules: Dict[str, Dict[str, float]] = {}
        raw_rules = raw.get("pairwise_rules", {})
        if isinstance(raw_rules, dict):
            for source_id, targets in raw_rules.items():
                if not isinstance(targets, dict):
                    continue
                source_key = str(source_id).strip().lower()
                if source_key == "":
                    continue
                loaded_targets: Dict[str, float] = {}
                for target_id, coefficient in targets.items():
                    target_key = str(target_id).strip().lower()
                    if target_key == "":
                        continue
                    try:
                        loaded_targets[target_key] = max(0.0, min(1.0, float(coefficient)))
                    except (TypeError, ValueError):
                        continue
                if loaded_targets:
                    loaded_rules[source_key] = loaded_targets
        if loaded_rules:
            self.field_interaction_rules = loaded_rules

        fallback = raw.get("fallback_positive_suppresses_negative", None)
        try:
            if fallback is not None:
                fallback_value = max(0.0, min(1.0, float(fallback)))
                self.field_interaction_profiles["positive_suppresses_negative"]["coefficient"] = fallback_value
        except (TypeError, ValueError):
            pass

    def create_session(self, player_id: Optional[str] = None, entitlements: Optional[List[str]] = None) -> Session:
        session_id = uuid.uuid4().hex
        resolved_player_id = str(player_id or "").strip()
        if resolved_player_id == "":
            resolved_player_id = f"session_{session_id[:8]}" if self.require_character_creation else "player"
        granted = self.entitlement_guard.apply_defaults(list(entitlements or []))
        session = Session(session_id=session_id, player_id=resolved_player_id)
        session.entitlements = granted
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

    def finite_adventure_policy_value(self, key: str, default: Any = None) -> Any:
        raw = getattr(self.feature_profile, "raw", {})
        if not isinstance(raw, dict):
            return default
        node = raw.get("finite_adventure", {})
        if not isinstance(node, dict):
            return default
        return node.get(key, default)

    def finite_adventure_default_campaign_id(self) -> str:
        configured = str(self.finite_adventure_policy_value("default_campaign_id", "")).strip()
        if configured:
            return configured
        definitions = sorted(self.world.campaign_manager.definitions.keys())
        if len(definitions) == 1:
            return definitions[0]
        return ""

    def finite_adventure_replay_supported(self) -> bool:
        raw_value = self.finite_adventure_policy_value("replay_supported", True)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        return bool(raw_value)

    def finite_adventure_checkpoint_policy(self) -> str:
        raw_value = self.finite_adventure_policy_value("checkpoint_policy", "manual_save")
        normalized = str(raw_value).strip().lower()
        return normalized or "manual_save"

    def finite_adventure_checkpoint_supported(self) -> bool:
        return self.finite_adventure_checkpoint_policy() not in {"disabled", "off", "none"}

    def _active_campaign_id_for_player(self, player: Any) -> str:
        if player is None:
            return ""
        active_campaigns = player.runtime_state.quests.active_campaigns
        if isinstance(active_campaigns, dict) and active_campaigns:
            return str(next(iter(active_campaigns.keys()), ""))
        return ""

    def _completed_campaign_id_for_player(self, player: Any) -> str:
        if player is None:
            return ""
        completed_campaigns = player.runtime_state.quests.completed_campaigns
        if isinstance(completed_campaigns, dict) and completed_campaigns:
            return str(next(reversed(list(completed_campaigns.keys())), ""))
        return ""

    def _campaign_name(self, campaign_id: str) -> str:
        if campaign_id == "":
            return ""
        definition = self.world.campaign_manager.definitions.get(campaign_id)
        if definition is None:
            return campaign_id
        return str(getattr(definition, "name", campaign_id))

    def _build_finite_adventure_summary_payload_from_summary(self, summary: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "available": False,
            "summary_version": 0,
            "campaign_id": "",
            "campaign_name": "",
            "status": "",
            "outcome": "",
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "final_node": "",
            "history": [],
            "resolution_counts": {},
            "history_count": 0,
            "player_name": "",
            "player_level": 0,
            "player_gold": 0,
            "final_health": 0,
            "max_health": 0,
            "final_mana": 0,
            "max_mana": 0,
            "quest_log_count": 0,
            "completed_quest_count": 0,
            "archived_quest_count": 0,
            "world_mode": "",
            "report_formats": ["text", "markdown", "json"],
        }
        if not isinstance(summary, dict):
            return payload

        started_at = summary.get("started_at")
        completed_at = summary.get("completed_at")
        duration_seconds = None
        if isinstance(started_at, (int, float)) and isinstance(completed_at, (int, float)):
            duration_seconds = max(0.0, float(completed_at) - float(started_at))
        history = summary.get("history", [])
        if not isinstance(history, list):
            history = []
        resolution_counts: Dict[str, int] = {}
        for entry in history:
            if not isinstance(entry, dict):
                continue
            resolution = str(entry.get("resolution", "")).strip()
            if resolution:
                resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1

        payload.update(
            {
                "available": True,
                "summary_version": int(summary.get("summary_version", 1)),
                "campaign_id": str(summary.get("campaign_id", "")),
                "campaign_name": str(summary.get("campaign_name", "")),
                "status": str(summary.get("status", "")),
                "outcome": str(summary.get("outcome", "")),
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds,
                "final_node": str(summary.get("final_node", "")),
                "history": history,
                "resolution_counts": resolution_counts,
                "history_count": len(history),
                "player_name": str(summary.get("player_name", "")),
                "player_level": int(summary.get("player_level", 0)),
                "player_gold": int(summary.get("player_gold", 0)),
                "final_health": int(summary.get("final_health", 0)),
                "max_health": int(summary.get("max_health", 0)),
                "final_mana": int(summary.get("final_mana", 0)),
                "max_mana": int(summary.get("max_mana", 0)),
                "quest_log_count": int(summary.get("quest_log_count", 0)),
                "completed_quest_count": int(summary.get("completed_quest_count", 0)),
                "archived_quest_count": int(summary.get("archived_quest_count", 0)),
                "world_mode": str(summary.get("world_mode", "")),
            }
        )
        return payload

    def _build_finite_adventure_summary_for_player(
        self,
        player: Any,
        campaign_id: str,
        status: str,
        outcome: str,
        final_node: str,
        completed_at: float | None = None,
    ) -> Dict[str, Any]:
        finite_state = player.runtime_state.quests.finite_adventure
        if not isinstance(finite_state, dict):
            finite_state = {}
        started_at = finite_state.get("started_at")
        history: List[Dict[str, Any]] = []
        active_campaigns = player.runtime_state.quests.active_campaigns
        completed_campaigns = player.runtime_state.quests.completed_campaigns
        campaign_state = {}
        if isinstance(active_campaigns, dict):
            campaign_state = active_campaigns.get(campaign_id, {})
        if (not isinstance(campaign_state, dict) or not campaign_state) and isinstance(completed_campaigns, dict):
            campaign_state = completed_campaigns.get(campaign_id, {})
        if isinstance(campaign_state, dict):
            raw_history = campaign_state.get("history", [])
            if isinstance(raw_history, list):
                history = copy.deepcopy(raw_history)
        resolved_completed_at = completed_at if completed_at is not None else time.time()
        return {
            "summary_version": 2,
            "campaign_id": campaign_id,
            "campaign_name": self._campaign_name(campaign_id),
            "status": str(status),
            "outcome": str(outcome),
            "started_at": started_at,
            "completed_at": resolved_completed_at,
            "final_node": str(final_node),
            "history": history,
            "player_name": str(getattr(player, "name", "")),
            "player_level": int(player.runtime_state.progression.level),
            "player_gold": int(player.runtime_state.gold),
            "final_health": int(getattr(player, "health", 0)),
            "max_health": int(getattr(player, "max_health", 0)),
            "final_mana": int(player.runtime_state.magic.mana),
            "max_mana": int(player.runtime_state.magic.max_mana),
            "quest_log_count": len(player.runtime_state.quests.active),
            "completed_quest_count": len(player.runtime_state.quests.completed),
            "archived_quest_count": len(player.runtime_state.quests.archived),
            "world_mode": str(self.feature_profile.resolved_world_mode()),
        }

    def build_finite_adventure_summary_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if player is None:
            return self._build_finite_adventure_summary_payload_from_summary({})
        finite_state = player.runtime_state.quests.finite_adventure
        if not isinstance(finite_state, dict):
            return self._build_finite_adventure_summary_payload_from_summary({})
        return self._build_finite_adventure_summary_payload_from_summary(finite_state.get("last_summary", {}))

    def build_finite_adventure_report_payload(self, session_id: str, format_name: str = "text") -> Dict[str, Any]:
        summary = self.build_finite_adventure_summary_payload(session_id)
        normalized = str(format_name).strip().lower() or "text"
        if normalized not in {"text", "markdown", "json"}:
            normalized = "text"
        payload: Dict[str, Any] = {
            "available": bool(summary.get("available")),
            "format": normalized,
            "content": "",
            "file_name_hint": "",
            "campaign_id": str(summary.get("campaign_id", "")),
        }
        if not bool(summary.get("available")):
            return payload
        campaign_id = str(summary.get("campaign_id", "")) or "adventure"
        safe_campaign_id = "".join(ch for ch in campaign_id if ch.isalnum() or ch in {"_", "-"}).strip() or "adventure"
        if normalized == "json":
            payload["content"] = json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True)
            payload["file_name_hint"] = f"{safe_campaign_id}_summary.json"
            return payload
        if normalized == "markdown":
            lines = [
                f"# Adventure Summary: {summary.get('campaign_name') or summary.get('campaign_id') or '(unknown)'}",
                "",
                f"- Status: `{summary.get('status', '')}`",
                f"- Outcome: `{summary.get('outcome', '')}`",
                f"- Final node: `{summary.get('final_node', '')}`",
                f"- Duration: `{summary.get('duration_seconds')}` seconds",
                f"- Player: `{summary.get('player_name', '')}` (level {summary.get('player_level', 0)})",
                f"- Final vitals: HP {summary.get('final_health', 0)}/{summary.get('max_health', 0)}, Mana {summary.get('final_mana', 0)}/{summary.get('max_mana', 0)}",
                f"- Gold: `{summary.get('player_gold', 0)}`",
                f"- Quest counts: active {summary.get('quest_log_count', 0)}, completed {summary.get('completed_quest_count', 0)}, archived {summary.get('archived_quest_count', 0)}",
                "",
                "## Resolution Counts",
            ]
            resolution_counts = summary.get("resolution_counts", {})
            if isinstance(resolution_counts, dict) and resolution_counts:
                for key in sorted(resolution_counts.keys()):
                    lines.append(f"- `{key}`: {resolution_counts[key]}")
            else:
                lines.append("- none")
            lines.append("")
            lines.append("## History")
            history = summary.get("history", [])
            if isinstance(history, list) and history:
                for entry in history:
                    if not isinstance(entry, dict):
                        continue
                    lines.append(
                        f"- `{entry.get('node_id', '?')}` via `{entry.get('resolution', '?')}`"
                    )
            else:
                lines.append("- none")
            payload["content"] = "\n".join(lines)
            payload["file_name_hint"] = f"{safe_campaign_id}_summary.md"
            return payload

        payload["content"] = self._format_finite_adventure_summary_text(session_id)
        payload["file_name_hint"] = f"{safe_campaign_id}_summary.txt"
        return payload

    def build_finite_adventure_catalog_payload(self) -> Dict[str, Any]:
        default_campaign_id = self.finite_adventure_default_campaign_id()
        entries: List[Dict[str, Any]] = []
        definitions = getattr(self.world.campaign_manager, "definitions", {})
        if isinstance(definitions, dict):
            for campaign_id in sorted(definitions.keys()):
                definition = definitions.get(campaign_id)
                if definition is None:
                    continue
                description = str(getattr(definition, "description", "")).strip()
                entries.append(
                    {
                        "campaign_id": str(campaign_id),
                        "name": str(getattr(definition, "name", campaign_id)),
                        "description": description,
                        "start_node_id": str(getattr(definition, "start_node_id", "")),
                        "node_count": len(getattr(definition, "nodes", {}) or {}),
                        "is_default": str(campaign_id) == default_campaign_id,
                    }
                )
        return {
            "enabled": self.feature_profile.resolved_world_mode() == "finite_adventure",
            "default_campaign_id": default_campaign_id,
            "campaigns": entries,
        }

    def _build_finite_adventure_world_baseline(self) -> Dict[str, Any]:
        dynamic_regions = []
        for region_id, region in self.world.regions.items():
            if region_id.startswith("dynamic_") or region_id.startswith("instance_"):
                dynamic_regions.append(copy.deepcopy(region.to_dict()))

        region_states: Dict[str, Dict[str, Any]] = {}
        room_states: Dict[str, Dict[str, Any]] = {}
        room_items_state: Dict[str, List[Dict[str, Any]]] = {}
        for region_id, region in self.world.regions.items():
            if not region:
                continue
            region_states[str(region_id)] = {
                "properties": copy.deepcopy(getattr(region, "properties", {})),
            }
            for room_id, room in region.rooms.items():
                if not room or not hasattr(room, "items"):
                    continue
                room_states[f"{region_id}:{room_id}"] = {
                    "visited": bool(getattr(room, "visited", False)),
                    "properties": copy.deepcopy(getattr(room, "properties", {})),
                    "env_properties": copy.deepcopy(getattr(room, "env_properties", {})),
                    "time_descriptions": copy.deepcopy(getattr(room, "time_descriptions", {})),
                }
                room_items_state[f"{region_id}:{room_id}"] = [
                    _serialize_item_reference(item, 1, self.world)
                    for item in getattr(room, "items", [])
                    if item
                ]

        npc_states = {
            instance_id: copy.deepcopy(npc.to_dict())
            for instance_id, npc in self.world.npcs.items()
            if npc and not npc.properties.get("is_summoned", False)
        }

        field_states: Dict[str, Dict[str, Any]] = {}
        for field_id, heartbeat in self.fields.items():
            field_states[str(field_id)] = {
                "cells": copy.deepcopy(heartbeat.snapshot()),
                "tick_index": int(getattr(heartbeat, "tick_index", 0)),
                "polarity": str(self.field_polarities.get(field_id, self._classify_polarity(field_id))),
            }

        return {
            "dynamic_regions": dynamic_regions,
            "region_states": region_states,
            "room_states": room_states,
            "room_items_state": room_items_state,
            "npc_states": npc_states,
            "quest_board": copy.deepcopy(self.world.quest_board),
            "respawn_queue": copy.deepcopy(self.world.respawn_manager.respawn_queue),
            "time_state": self.time_manager.get_time_state_for_save(),
            "weather_state": self.weather_manager.get_weather_state_for_save(),
            "field_states": field_states,
            "default_field_id": str(getattr(self, "default_field_id", "blight")),
            "default_field_polarity": str(getattr(self, "default_field_polarity", "negative")),
        }

    def _restore_finite_adventure_world_baseline(self, baseline: Any) -> bool:
        if not isinstance(baseline, dict):
            return False

        removable_regions = [
            region_id
            for region_id in list(self.world.regions.keys())
            if str(region_id).startswith("dynamic_") or str(region_id).startswith("instance_")
        ]
        for region_id in removable_regions:
            self.world.regions.pop(region_id, None)

        self.world.initialize_new_world(
            start_region=str(getattr(self.world, "bootstrap_start_region", "") or self.content_set.start_region_id),
            start_room=str(getattr(self.world, "bootstrap_start_room", "") or self.content_set.start_room_id),
        )

        self.world.quest_board = copy.deepcopy(baseline.get("quest_board", []))
        self.world.respawn_manager.respawn_queue = copy.deepcopy(baseline.get("respawn_queue", []))

        for region_data in baseline.get("dynamic_regions", []):
            if not isinstance(region_data, dict):
                continue
            try:
                region = Region.from_dict(copy.deepcopy(region_data))
                self.world.add_region(region.obj_id, region)
            except Exception:
                continue

        region_states = baseline.get("region_states", {})
        if isinstance(region_states, dict):
            for region_id, state in region_states.items():
                region = self.world.regions.get(str(region_id))
                if not region or not isinstance(state, dict):
                    continue
                region.properties = copy.deepcopy(state.get("properties", {}))

        room_states = baseline.get("room_states", {})
        if isinstance(room_states, dict):
            for room_key, state in room_states.items():
                if not isinstance(room_key, str) or ":" not in room_key or not isinstance(state, dict):
                    continue
                region_id, room_id = room_key.split(":", 1)
                region = self.world.regions.get(region_id)
                room = region.get_room(room_id) if region else None
                if not room:
                    continue
                room.visited = bool(state.get("visited", False))
                room.properties = copy.deepcopy(state.get("properties", {}))
                room.env_properties = copy.deepcopy(state.get("env_properties", {}))
                room.time_descriptions = copy.deepcopy(state.get("time_descriptions", {}))
                room.active_env_effects = []
                room._hazard_last_tick_by_entity = {}
                room.update_property("exits", room.exits)
                room.update_property("visited", room.visited)
                room.update_property("time_descriptions", room.time_descriptions)
                room.update_property("env_properties", room.env_properties)

        for region in self.world.regions.values():
            if not region:
                continue
            for room in region.rooms.values():
                if room:
                    room.items = []

        self.world.npcs = {}
        for instance_id, npc_state in baseline.get("npc_states", {}).items():
            if not isinstance(npc_state, dict):
                continue
            template_id = npc_state.get("template_id")
            if not template_id:
                continue
            overrides = copy.deepcopy(npc_state)
            overrides.pop("template_id", None)
            npc = NPCFactory.create_npc_from_template(template_id, self.world, instance_id, **overrides)
            if npc:
                self.world.add_npc(npc)

        initialize_npc_schedules(self.world)
        self.world._load_room_items_from_save(copy.deepcopy(baseline.get("room_items_state", {})))
        self.time_manager.apply_loaded_time_state(copy.deepcopy(baseline.get("time_state")))
        self.weather_manager.apply_loaded_weather_state(copy.deepcopy(baseline.get("weather_state")))

        self.fields = {}
        self.field_polarities = {}
        field_states = baseline.get("field_states", {})
        if isinstance(field_states, dict):
            for field_id, state in field_states.items():
                if not isinstance(field_id, str) or not isinstance(state, dict):
                    continue
                heartbeat = self._ensure_field(field_id)
                heartbeat.load_cells(copy.deepcopy(state.get("cells", {})))
                heartbeat.tick_index = int(state.get("tick_index", 0))
                self.field_polarities[field_id] = str(state.get("polarity", self._classify_polarity(field_id)))
        self.default_field_id = str(baseline.get("default_field_id", self.default_field_id or "blight"))
        self.default_field_polarity = str(
            baseline.get(
                "default_field_polarity",
                self.field_polarities.get(self.default_field_id, self._classify_polarity(self.default_field_id)),
            )
        )
        return True

    def build_finite_adventure_state_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        payload: Dict[str, Any] = {
            "enabled": self.feature_profile.resolved_world_mode() == "finite_adventure",
            "default_campaign_id": self.finite_adventure_default_campaign_id(),
            "replay_supported": self.finite_adventure_replay_supported(),
            "checkpoint_policy": self.finite_adventure_checkpoint_policy(),
            "checkpoint_available": False,
            "checkpoint_saved_at": None,
            "checkpoint_campaign_id": "",
            "checkpoint_node": "",
            "last_summary_available": False,
            "status": "not_started",
            "campaign_id": "",
            "current_node": "",
            "outcome": "",
            "started_at": None,
            "completed_at": None,
        }
        if player is None:
            return payload
        state = player.runtime_state.quests.finite_adventure
        if isinstance(state, dict):
            payload["status"] = str(state.get("status", payload["status"]))
            payload["campaign_id"] = str(state.get("campaign_id", payload["campaign_id"]))
            payload["current_node"] = str(state.get("current_node", payload["current_node"]))
            payload["outcome"] = str(state.get("outcome", payload["outcome"]))
            payload["started_at"] = state.get("started_at")
            payload["completed_at"] = state.get("completed_at")
            checkpoint = state.get("checkpoint", {})
            if isinstance(checkpoint, dict):
                payload["checkpoint_available"] = bool(checkpoint.get("player_snapshot"))
                payload["checkpoint_saved_at"] = checkpoint.get("saved_at")
                payload["checkpoint_campaign_id"] = str(checkpoint.get("campaign_id", ""))
                payload["checkpoint_node"] = str(checkpoint.get("current_node", ""))
            payload["last_summary_available"] = isinstance(state.get("last_summary", {}), dict) and bool(state.get("last_summary"))

        if payload["campaign_id"] == "":
            payload["campaign_id"] = self._active_campaign_id_for_player(player) or self._completed_campaign_id_for_player(player)

        active_campaign_id = self._active_campaign_id_for_player(player)
        if active_campaign_id:
            payload["status"] = "active"
            payload["campaign_id"] = active_campaign_id
            active_state = player.runtime_state.quests.active_campaigns.get(active_campaign_id, {})
            if isinstance(active_state, dict):
                payload["current_node"] = str(active_state.get("current_node", payload["current_node"]))
        elif payload["status"] not in {"completed", "abandoned"}:
            payload["status"] = "not_started"

        completed_campaign_id = self._completed_campaign_id_for_player(player)
        if payload["status"] in {"completed", "abandoned"} and payload["campaign_id"] == "" and completed_campaign_id:
            payload["campaign_id"] = completed_campaign_id

        return payload

    def _format_finite_adventure_status_text(self, session_id: str) -> str:
        payload = self.build_finite_adventure_state_payload(session_id)
        default_campaign_id = str(payload.get("default_campaign_id", ""))
        status = str(payload.get("status", "not_started"))
        campaign_id = str(payload.get("campaign_id", ""))
        outcome = str(payload.get("outcome", ""))
        current_node = str(payload.get("current_node", ""))
        if status == "active":
            return f"Adventure active: {campaign_id or '(unknown)'} at node '{current_node or '?'}'."
        if status == "completed":
            return f"Adventure complete: {campaign_id or '(unknown)'} ended with outcome '{outcome or 'unknown'}'."
        if status == "abandoned":
            return f"Adventure abandoned: {campaign_id or '(unknown)'}."
        if default_campaign_id:
            checkpoint_text = ""
            if bool(payload.get("checkpoint_available")):
                checkpoint_text = f" Checkpoint available at '{payload.get('checkpoint_node', '?')}'."
            summary_text = ""
            if bool(payload.get("last_summary_available")):
                summary_text = " Last run summary is available."
            return f"No finite adventure run started. Default campaign: {default_campaign_id}.{checkpoint_text}{summary_text}"
        return "No finite adventure run started."

    def _format_finite_adventure_summary_text(self, session_id: str) -> str:
        summary = self.build_finite_adventure_summary_payload(session_id)
        if not summary.get("available"):
            return "No finite adventure run summary is available yet."
        campaign_name = str(summary.get("campaign_name", "")) or str(summary.get("campaign_id", "(unknown)"))
        status = str(summary.get("status", ""))
        outcome = str(summary.get("outcome", "")) or "unknown"
        history_count = int(summary.get("history_count", 0))
        final_node = str(summary.get("final_node", "")) or "?"
        duration_seconds = summary.get("duration_seconds")
        duration_text = ""
        if isinstance(duration_seconds, (int, float)):
            duration_text = f" Duration {float(duration_seconds):.1f}s."
        player_name = str(summary.get("player_name", "")).strip() or "Unknown"
        player_level = int(summary.get("player_level", 0))
        gold = int(summary.get("player_gold", 0))
        return (
            f"Last adventure summary: {campaign_name} ended with status '{status}' and outcome '{outcome}'. "
            f"Final node '{final_node}', {history_count} resolved node(s). "
            f"Player {player_name} (level {player_level}) finished with {gold} gold.{duration_text}"
        )

    def _build_finite_adventure_checkpoint(self, player: Any) -> Dict[str, Any]:
        snapshot = copy.deepcopy(player.to_dict(self.world))
        finite_state = snapshot.get("gameplay", {}).get("quests", {}).get("finite_adventure_state", {})
        if not isinstance(finite_state, dict):
            finite_state = {}
        finite_state["checkpoint"] = {}
        snapshot.setdefault("gameplay", {}).setdefault("quests", {})["finite_adventure_state"] = finite_state
        return {
            "saved_at": time.time(),
            "campaign_id": self._active_campaign_id_for_player(player) or self._completed_campaign_id_for_player(player),
            "current_node": str(finite_state.get("current_node", "")),
            "player_snapshot": snapshot,
        }

    def _apply_player_snapshot(self, player: Any, snapshot: Dict[str, Any]) -> bool:
        if player is None or not isinstance(snapshot, dict):
            return False
        from engine.player.core import Player

        restored = Player.from_dict(copy.deepcopy(snapshot), self.world)
        if restored is None:
            return False
        player.__dict__.clear()
        player.__dict__.update(restored.__dict__)
        player.world = self.world
        self.world.players[player.obj_id] = player
        return True

    def _restore_finite_adventure_checkpoint(self, player: Any) -> tuple[bool, str]:
        if player is None:
            return False, "No character yet. Use: char create <name>"
        finite_state = player.runtime_state.quests.finite_adventure
        if not isinstance(finite_state, dict):
            return False, "No finite adventure checkpoint is available."
        checkpoint = finite_state.get("checkpoint", {})
        if not isinstance(checkpoint, dict):
            return False, "No finite adventure checkpoint is available."
        snapshot = checkpoint.get("player_snapshot")
        if not isinstance(snapshot, dict):
            return False, "No finite adventure checkpoint is available."
        if not self._apply_player_snapshot(player, snapshot):
            return False, "Failed to restore the finite adventure checkpoint."
        restored_state = player.runtime_state.quests.finite_adventure
        if not isinstance(restored_state, dict):
            restored_state = {}
        restored_state["checkpoint"] = copy.deepcopy(checkpoint)
        restored_state["status"] = "active"
        restored_state["campaign_id"] = str(checkpoint.get("campaign_id", restored_state.get("campaign_id", "")))
        restored_state["current_node"] = str(checkpoint.get("current_node", restored_state.get("current_node", "")))
        restored_state["outcome"] = ""
        restored_state["completed_at"] = None
        player.runtime_state.quests.finite_adventure = restored_state
        return True, f"Finite adventure restored from checkpoint: {restored_state.get('campaign_id', '(unknown)')}"

    def _reset_finite_adventure_player_state(self, player: Any, campaign_id: str = "") -> None:
        if player is None:
            return
        if campaign_id:
            player.runtime_state.quests.active_campaigns.pop(campaign_id, None)
            player.runtime_state.quests.completed_campaigns.pop(campaign_id, None)
        else:
            player.runtime_state.quests.active_campaigns = {}
            player.runtime_state.quests.completed_campaigns = {}
        player.runtime_state.quests.active = {}
        player.runtime_state.quests.completed = {}
        player.runtime_state.quests.archived = {}
        player.health = int(getattr(player, "max_health", 0))
        player.runtime_state.magic.mana = int(player.runtime_state.magic.max_mana)
        player.is_alive = True
        player.runtime_state.combat.in_combat = False
        player.runtime_state.combat.target = None
        player.runtime_state.combat.targets = set()
        player.combat_messages = []
        player.active_effects = []
        player.runtime_state.magic.cooldowns = {}
        player.runtime_state.magic.summons = {}
        player.active_minigame = None
        player.trading_with = None
        player.follow_target = None
        player.last_talked_to = None
        player.current_region_id = str(getattr(self.world, "bootstrap_start_region", "") or player.respawn_region_id or self.content_set.start_region_id)
        player.current_room_id = str(getattr(self.world, "bootstrap_start_room", "") or player.respawn_room_id or self.content_set.start_room_id)

    def record_finite_adventure_summary(
        self,
        player: Any,
        campaign_id: str,
        status: str,
        outcome: str,
        final_node: str,
        completed_at: float | None = None,
    ) -> Dict[str, Any]:
        if player is None:
            return {}
        finite_state = player.runtime_state.quests.finite_adventure
        if not isinstance(finite_state, dict):
            finite_state = {}
        summary = self._build_finite_adventure_summary_for_player(
            player,
            campaign_id=campaign_id,
            status=status,
            outcome=outcome,
            final_node=final_node,
            completed_at=completed_at,
        )
        finite_state["last_summary"] = summary
        player.runtime_state.quests.finite_adventure = finite_state
        return summary

    def _try_handle_finite_adventure_command(self, session_id: str, text: str) -> tuple[bool, List[Dict[str, Any]]]:
        if self.feature_profile.resolved_world_mode() != "finite_adventure" or not self.world.has_capability("quests"):
            return False, []

        normalized = str(text).strip()
        lowered = normalized.lower()
        if not lowered.startswith("adventure"):
            return False, []

        parts = normalized.split()
        subcommand = parts[1].lower() if len(parts) > 1 else "status"
        if subcommand in {"list", "catalog", "campaigns"}:
            catalog_payload = self.build_finite_adventure_catalog_payload()
            campaigns = catalog_payload.get("campaigns", [])
            count = len(campaigns) if isinstance(campaigns, list) else 0
            default_campaign_id = str(catalog_payload.get("default_campaign_id", "")).strip()
            summary_text = "Finite adventure campaigns: %d available" % count
            if default_campaign_id != "":
                summary_text += " (default: %s)" % default_campaign_id
            return True, [
                self._event("text", session_id, summary_text),
                self._event("finite_adventure_catalog", session_id, catalog_payload),
            ]

        player = self.get_player_for_session(session_id)
        if player is None:
            return True, [self._event("text", session_id, "No character yet. Use: char create <name>")]

        if subcommand in {"status", "state"}:
            return True, [
                self._event("text", session_id, self._format_finite_adventure_status_text(session_id)),
                self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]

        if subcommand == "summary":
            report_format = str(parts[2]).strip().lower() if len(parts) >= 3 else "text"
            if report_format in {"text", "markdown", "json"}:
                report_payload = self.build_finite_adventure_report_payload(session_id, report_format)
                return True, [
                    self._event("text", session_id, self._format_finite_adventure_summary_text(session_id)),
                    self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
                    self._event("finite_adventure_report", session_id, report_payload),
                ]
            return True, [
                self._event("text", session_id, self._format_finite_adventure_summary_text(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]

        if subcommand == "start":
            requested_campaign_id = str(parts[2]).strip() if len(parts) >= 3 else self.finite_adventure_default_campaign_id()
            if requested_campaign_id == "":
                return True, [self._event("text", session_id, "No campaign specified and no default finite-adventure campaign is configured.")]
            state_payload = self.build_finite_adventure_state_payload(session_id)
            if state_payload.get("status") == "active":
                return True, [self._event("text", session_id, "A finite adventure run is already active. Use: adventure status")]
            if state_payload.get("status") == "completed" and not self.finite_adventure_replay_supported():
                return True, [self._event("text", session_id, "Replay is disabled for this finite adventure profile.")]
            finite_state = player.runtime_state.quests.finite_adventure
            if not isinstance(finite_state, dict):
                finite_state = {}
            finite_state["world_baseline"] = self._build_finite_adventure_world_baseline()
            player.runtime_state.quests.finite_adventure = finite_state
            started = self.world.campaign_manager.start_campaign(requested_campaign_id, player)
            if not started:
                return True, [self._event("text", session_id, f"Failed to start finite adventure campaign '{requested_campaign_id}'.")]
            return True, [
                self._event("text", session_id, f"Finite adventure started: {requested_campaign_id}"),
                self._event("quests", session_id, self._build_quests_payload(session_id)),
                self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]

        if subcommand == "checkpoint":
            if not self.finite_adventure_checkpoint_supported():
                return True, [self._event("text", session_id, "Checkpoint saves are disabled for this finite adventure profile.")]
            state_payload = self.build_finite_adventure_state_payload(session_id)
            if state_payload.get("status") != "active":
                return True, [self._event("text", session_id, "A finite adventure checkpoint can only be created during an active run.")]
            finite_state = player.runtime_state.quests.finite_adventure
            if not isinstance(finite_state, dict):
                finite_state = {}
            finite_state["checkpoint"] = self._build_finite_adventure_checkpoint(player)
            player.runtime_state.quests.finite_adventure = finite_state
            self.persist_player_snapshot(session_id)
            return True, [
                self._event("text", session_id, f"Finite adventure checkpoint saved at node '{finite_state['checkpoint'].get('current_node', '?')}'."),
                self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]

        if subcommand == "restore":
            if not self.finite_adventure_checkpoint_supported():
                return True, [self._event("text", session_id, "Checkpoint restore is disabled for this finite adventure profile.")]
            ok, message = self._restore_finite_adventure_checkpoint(player)
            if ok:
                self.persist_player_snapshot(session_id)
                return True, [
                    self._event("text", session_id, message),
                    self._event("status", session_id, self._build_status_payload(session_id)),
                    self._event("nearby", session_id, self._build_nearby_payload(session_id)),
                    self._event("quests", session_id, self._build_quests_payload(session_id)),
                    self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                    self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
                ]
            return True, [self._event("text", session_id, message)]

        if subcommand == "abandon":
            state_payload = self.build_finite_adventure_state_payload(session_id)
            if state_payload.get("status") != "active":
                return True, [self._event("text", session_id, "No active finite adventure run to abandon.")]
            campaign_id = str(state_payload.get("campaign_id", ""))
            checkpoint = copy.deepcopy(player.runtime_state.quests.finite_adventure.get("checkpoint", {}))
            world_baseline = copy.deepcopy(player.runtime_state.quests.finite_adventure.get("world_baseline", {}))
            summary = self.record_finite_adventure_summary(
                player,
                campaign_id=campaign_id,
                status="abandoned",
                outcome="ABANDON",
                final_node=str(state_payload.get("current_node", "")),
                completed_at=time.time(),
            )
            self._reset_finite_adventure_player_state(player, campaign_id)
            player.runtime_state.quests.finite_adventure = {
                "campaign_id": campaign_id,
                "status": "abandoned",
                "current_node": "",
                "started_at": state_payload.get("started_at"),
                "completed_at": summary.get("completed_at"),
                "outcome": "ABANDON",
                "checkpoint": checkpoint,
                "last_summary": summary,
                "world_baseline": world_baseline,
            }
            self.persist_player_snapshot(session_id)
            return True, [
                self._event("text", session_id, f"Finite adventure abandoned: {campaign_id or '(unknown)'}"),
                self._event("quests", session_id, self._build_quests_payload(session_id)),
                self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]

        if subcommand in {"reset", "replay"}:
            state_payload = self.build_finite_adventure_state_payload(session_id)
            if state_payload.get("status") == "active":
                return True, [self._event("text", session_id, "Cannot reset while a finite adventure run is active. Use: adventure abandon")]
            if subcommand == "replay" and not self.finite_adventure_replay_supported():
                return True, [self._event("text", session_id, "Replay is disabled for this finite adventure profile.")]
            campaign_id = str(state_payload.get("campaign_id", "")) or self.finite_adventure_default_campaign_id()
            prior_finite_state = player.runtime_state.quests.finite_adventure
            prior_baseline = copy.deepcopy(prior_finite_state.get("world_baseline", {})) if isinstance(prior_finite_state, dict) else {}
            if prior_baseline:
                self._restore_finite_adventure_world_baseline(prior_baseline)
            self._reset_finite_adventure_player_state(player, campaign_id)
            prior_summary = copy.deepcopy(player.runtime_state.quests.finite_adventure.get("last_summary", {}))
            player.runtime_state.quests.finite_adventure = {
                "campaign_id": campaign_id,
                "status": "not_started",
                "current_node": "",
                "started_at": None,
                "completed_at": None,
                "outcome": "",
                "checkpoint": {},
                "last_summary": prior_summary,
                "world_baseline": prior_baseline,
            }
            self.persist_player_snapshot(session_id)
            events = [
                self._event("text", session_id, f"Finite adventure reset: {campaign_id or '(default)'}"),
                self._event("status", session_id, self._build_status_payload(session_id)),
                self._event("nearby", session_id, self._build_nearby_payload(session_id)),
                self._event("quests", session_id, self._build_quests_payload(session_id)),
                self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)),
                self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)),
            ]
            if subcommand == "replay" and campaign_id:
                started = self.world.campaign_manager.start_campaign(campaign_id, player)
                if started:
                    events.append(self._event("text", session_id, f"Finite adventure started: {campaign_id}"))
                    events.append(self._event("quests", session_id, self._build_quests_payload(session_id)))
                    events.append(self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)))
                    events.append(self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)))
                else:
                    events.append(self._event("text", session_id, f"Failed to restart finite adventure campaign '{campaign_id}'."))
            return True, events

        return True, [self._event("text", session_id, "Usage: adventure status | list | summary [text|markdown|json] | start [campaign_id] | checkpoint | restore | abandon | reset | replay")]

    def build_party_state_payload(self, session_id: str) -> Dict[str, Any]:
        session = self.sessions.get(session_id)
        mode = self.feature_profile.resolved_world_mode()
        if session is None:
            return {
                "supported": mode == "co_op_party",
                "mode": mode,
                "in_party": False,
                "party_id": "",
                "leader_player_id": "",
                "leader_name": "",
                "members": [],
                "pending_invites": [],
                "outgoing_invites": [],
            }

        player_id = str(session.player_id)
        party = self._party_for_player_id(player_id)
        pending_party_id = self.pending_party_invites.get(player_id, "")
        pending_invites: List[Dict[str, Any]] = []
        if pending_party_id and pending_party_id in self.parties:
            inviter_party = self.parties[pending_party_id]
            pending_invites.append(
                {
                    "party_id": inviter_party.party_id,
                    "leader_player_id": inviter_party.leader_player_id,
                    "leader_name": self._display_name_for_player_id(inviter_party.leader_player_id),
                }
            )
        outgoing_invites: List[Dict[str, Any]] = []
        if party is not None and party.leader_player_id == player_id:
            for invited_player_id in self._pending_invitees_for_party(party.party_id):
                outgoing_invites.append(
                    {
                        "player_id": invited_player_id,
                        "name": self._display_name_for_player_id(invited_player_id),
                    }
                )

        if party is None:
            return {
                "supported": mode == "co_op_party",
                "mode": mode,
                "in_party": False,
                "party_id": "",
                "leader_player_id": "",
                "leader_name": "",
                "members": [],
                "pending_invites": pending_invites,
                "outgoing_invites": outgoing_invites,
            }

        members: List[Dict[str, Any]] = []
        for member_player_id in party.member_player_ids:
            online_session = self._find_online_session_by_player_id(member_player_id)
            members.append(
                {
                    "player_id": member_player_id,
                    "name": self._display_name_for_player_id(member_player_id),
                    "is_leader": member_player_id == party.leader_player_id,
                    "online": online_session is not None,
                    "session_id": getattr(online_session, "session_id", ""),
                }
            )

        return {
            "supported": mode == "co_op_party",
            "mode": mode,
            "in_party": True,
            "party_id": party.party_id,
            "leader_player_id": party.leader_player_id,
            "leader_name": self._display_name_for_player_id(party.leader_player_id),
            "members": members,
            "pending_invites": pending_invites,
            "outgoing_invites": outgoing_invites,
        }

    def get_player_for_session(self, session_id: str) -> Any:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return self.world.players.get(session.player_id)

    def _handle_character_creation_command(self, session_id: str, text: str) -> tuple[bool, str, bool]:
        normalized = str(text).strip()
        lowered = normalized.lower()
        if lowered in {"help", "?", "char help", "character help"}:
            return True, "Create your character with: char create <name>", False

        prefix = None
        if lowered.startswith("char create "):
            prefix = "char create "
        elif lowered.startswith("character create "):
            prefix = "character create "
        if prefix is None:
            return False, "", False

        raw_name = normalized[len(prefix):].strip()
        if len(raw_name) < 3 or len(raw_name) > 24:
            return True, "Character name must be 3-24 characters.", False
        if not re.fullmatch(r"[A-Za-z0-9 _'\-]+", raw_name):
            return True, "Character name contains unsupported characters.", False

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
        new_player = Player(raw_name, data_root=self.world.data_root)
        new_player.obj_id = session.player_id
        new_player.world = self.world
        self.world.initialize_content_player(new_player)
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
        return True, f"Character created: {raw_name}", True

    def build_opening_guidance(self) -> str:
        """Format the selected content set's optional first-session brief."""
        opening = getattr(self.content_set, "opening", {}) if self.content_set else {}
        if not isinstance(opening, dict):
            return ""
        heading = str(opening.get("heading", "")).strip()
        intro = str(opening.get("intro", "")).strip()
        objectives = opening.get("objectives", [])
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
                lines.append("First steps:\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1)))
        return "\n\n".join(lines)

    def _party_for_player_id(self, player_id: str) -> Party | None:
        party_id = self.player_party_membership.get(str(player_id), "")
        if party_id == "":
            return None
        return self.parties.get(party_id)

    def party_policy_value(self, key: str, default: Any = None) -> Any:
        raw = getattr(self.feature_profile, "raw", {})
        if not isinstance(raw, dict):
            return default
        party_node = raw.get("party", {})
        if not isinstance(party_node, dict):
            return default
        return party_node.get(key, default)

    def party_invite_conflict_policy(self) -> str:
        return str(self.party_policy_value("invite_conflict_policy", "replace_existing")).strip().lower() or "replace_existing"

    def party_offline_invites_supported(self) -> bool:
        raw_value = self.party_policy_value("offline_invites_supported", True)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        return bool(raw_value)

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

    def _party_impacted_player_ids(self, player_id: str) -> List[str]:
        impacted_player_ids: List[str] = [str(player_id)]
        party = self._party_for_player_id(str(player_id))
        if party is not None:
            impacted_player_ids.extend(list(party.member_player_ids))

        pending_party_id = self.pending_party_invites.get(str(player_id), "")
        if pending_party_id:
            pending_party = self.parties.get(pending_party_id)
            if pending_party is not None:
                impacted_player_ids.extend(list(pending_party.member_player_ids))

        for invited_player_id in self._pending_invitees_for_party(self.player_party_membership.get(str(player_id), "")):
            impacted_player_ids.append(invited_player_id)
        return list(sorted(set(impacted_player_ids)))

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

    def party_member_player_ids(self, player_id: str) -> List[str]:
        party = self._party_for_player_id(player_id)
        if party is None:
            return [str(player_id)]
        return list(party.member_player_ids)

    def party_member_players(
        self,
        player_id: str,
        *,
        require_same_location_as: Any | None = None,
        require_connected: bool = False,
    ) -> List[Any]:
        players: List[Any] = []
        for member_id in self.party_member_player_ids(player_id):
            member = self.world.players.get(member_id)
            if member is None:
                continue
            if require_same_location_as is not None:
                if (
                    getattr(member, "current_region_id", None) != getattr(require_same_location_as, "current_region_id", None)
                    or getattr(member, "current_room_id", None) != getattr(require_same_location_as, "current_room_id", None)
                ):
                    continue
            if require_connected and self._find_online_session_by_player_id(member_id) is None:
                continue
            players.append(member)
        return players

    def distribute_party_loot(self, actor: Any, item: Any) -> tuple[Any, str]:
        actor_id = str(getattr(actor, "obj_id", ""))
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return actor, ""
        party = self._party_for_player_id(actor_id)
        if party is None:
            return actor, ""

        policy = str(self.party_policy_value("loot_policy", "round_robin")).strip().lower()
        eligible = self.party_member_players(
            actor_id,
            require_same_location_as=actor,
            require_connected=True,
        )
        if not eligible:
            return actor, ""

        recipient = actor
        if policy == "leader_discretion":
            leader = self.world.players.get(party.leader_player_id)
            if leader is not None and leader in eligible:
                recipient = leader
        elif policy == "finder_keep":
            recipient = actor
        else:
            full_roster: List[Any] = []
            for member_player_id in party.member_player_ids:
                member = self.world.players.get(member_player_id)
                if member is not None:
                    full_roster.append(member)
            if not full_roster:
                full_roster = list(eligible)
            eligible_ids = {str(getattr(player, "obj_id", "")) for player in eligible}
            cursor = self.party_loot_cursors.get(party.party_id, 0)
            recipient = actor
            selected_index = None
            for offset in range(len(full_roster)):
                index = (cursor + offset) % len(full_roster)
                candidate = full_roster[index]
                if str(getattr(candidate, "obj_id", "")) in eligible_ids:
                    recipient = candidate
                    selected_index = index
                    break
            if selected_index is None:
                recipient = actor
                selected_index = cursor % len(full_roster)
            self.party_loot_cursors[party.party_id] = (selected_index + 1) % len(full_roster)

        can_add, _msg = recipient.inventory.can_add_item(item)
        if not can_add:
            actor_can_add, _actor_msg = actor.inventory.can_add_item(item)
            if actor_can_add:
                recipient = actor
            else:
                return actor, ""

        if getattr(recipient, "obj_id", "") == getattr(actor, "obj_id", ""):
            return actor, ""
        return recipient, f"Loot policy routed {item.name} to {recipient.name}."

    def _reward_recipient_players(self, actor: Any) -> List[Any]:
        actor_id = str(getattr(actor, "obj_id", ""))
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return [actor]
        party = self._party_for_player_id(actor_id)
        if party is None:
            return [actor]

        policy = str(self.party_policy_value("shared_rewards_policy", "split")).strip().lower()
        if policy == "leader_claims":
            leader = self.world.players.get(party.leader_player_id)
            return [leader] if leader is not None else [actor]

        recipients = self.party_member_players(actor_id)
        return recipients or [actor]

    def party_reward_routing_active(self, actor: Any) -> bool:
        actor_id = str(getattr(actor, "obj_id", ""))
        if actor_id == "":
            return False
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return False
        return self._party_for_player_id(actor_id) is not None

    def _split_int_amount(self, total: int, count: int) -> List[int]:
        if count <= 0:
            return []
        base = total // count
        remainder = total % count
        values = [base for _ in range(count)]
        for index in range(remainder):
            values[index] += 1
        return values

    def grant_party_rewards(self, actor: Any, rewards: Dict[str, Any]) -> str:
        recipients = self._reward_recipient_players(actor)
        if not recipients:
            recipients = [actor]

        msgs: List[str] = []
        xp_total = int(rewards.get("xp", 0) or 0)
        gold_total = int(rewards.get("gold", 0) or 0)

        if xp_total > 0:
            for recipient, amount in zip(recipients, self._split_int_amount(xp_total, len(recipients))):
                if amount <= 0:
                    continue
                recipient.gain_experience(amount)
                msgs.append(f"{recipient.name} +{amount} XP")

        if gold_total > 0:
            for recipient, amount in zip(recipients, self._split_int_amount(gold_total, len(recipients))):
                if amount <= 0:
                    continue
                recipient.runtime_state.gold += amount
                msgs.append(f"{recipient.name} +{amount} Gold")

        item_rewards = rewards.get("items", [])
        if isinstance(item_rewards, list):
            from engine.items.item_factory import ItemFactory

            for item_data in item_rewards:
                item_id = str(item_data.get("item_id", "")).strip()
                quantity = int(item_data.get("quantity", 1) or 1)
                if item_id == "" or quantity <= 0:
                    continue
                for _ in range(quantity):
                    item = ItemFactory.create_item_from_template(item_id, self.world)
                    if item is None:
                        continue
                    recipient, _note = self.distribute_party_loot(actor, item)
                    recipient.inventory.add_item(item, 1)
                    msgs.append(f"{recipient.name} received {item.name}")

        generated_item_data = rewards.get("generated_item_data")
        if isinstance(generated_item_data, dict):
            from engine.items.item_factory import ItemFactory

            item = ItemFactory.from_dict(generated_item_data, actor.world)
            if item is not None:
                recipient, _note = self.distribute_party_loot(actor, item)
                recipient.inventory.add_item(item)
                msgs.append(f"{recipient.name} received {item.name}")

        if not msgs:
            return ""
        return "Rewards: " + ", ".join(msgs)

    def grant_party_gold(self, actor: Any, amount: int) -> str:
        total = int(amount or 0)
        if total <= 0:
            return ""
        recipients = self._reward_recipient_players(actor)
        if not recipients:
            recipients = [actor]

        msgs: List[str] = []
        for recipient, share in zip(recipients, self._split_int_amount(total, len(recipients))):
            if share <= 0:
                continue
            recipient.runtime_state.gold += share
            msgs.append(f"{recipient.name} +{share} Gold")
        return ", ".join(msgs)

    def _ensure_party_for_leader(self, leader_player_id: str) -> Party:
        existing = self._party_for_player_id(leader_player_id)
        if existing is not None:
            return existing
        party = Party(
            party_id="party_" + uuid.uuid4().hex[:10],
            leader_player_id=leader_player_id,
            member_player_ids=[leader_player_id],
        )
        self.parties[party.party_id] = party
        self.player_party_membership[leader_player_id] = party.party_id
        return party

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

    def _party_sync_events_for_player_ids(self, player_ids: List[str]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        seen_session_ids: set[str] = set()
        for session in self.sessions.values():
            if not getattr(session, "connected", False):
                continue
            if session.player_id not in player_ids:
                continue
            if session.session_id in seen_session_ids:
                continue
            seen_session_ids.add(session.session_id)
            events.append(
                self._event(
                    "party_state",
                    session.session_id,
                    self.build_party_state_payload(session.session_id),
                )
            )
        return events

    def build_party_presence_sync_events_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if session is None:
            return []
        return self._party_sync_events_for_player_ids(self._party_impacted_player_ids(str(session.player_id)))

    def mirror_party_quest_acceptance(self, actor: Any, new_quest_ids: List[str]) -> List[Dict[str, Any]]:
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return []
        if str(self.party_policy_value("shared_quest_policy", "leader_driven")).strip().lower() != "mirror_all":
            return []

        actor_id = str(getattr(actor, "obj_id", ""))
        party = self._party_for_player_id(actor_id)
        if party is None:
            return []

        events: List[Dict[str, Any]] = []
        for quest_id in new_quest_ids:
            quest_data = actor.runtime_state.quests.active.get(quest_id)
            if not isinstance(quest_data, dict):
                continue

            root_id = str(quest_data.get("party_shared_root_id", quest_id)).strip() or quest_id
            quest_data["party_shared_root_id"] = root_id
            quest_data["party_shared_party_id"] = party.party_id
            quest_data["party_shared_owner_player_id"] = actor_id

            for member_id in party.member_player_ids:
                if member_id == actor_id:
                    continue
                member = self.world.players.get(member_id)
                if member is None:
                    continue
                already_present = any(
                    str(existing.get("party_shared_root_id", "")) == root_id
                    for existing in (member.runtime_state.quests.active.values() if member.runtime_state.quests is not None else [])
                    if isinstance(existing, dict)
                )
                if already_present:
                    continue
                mirrored = copy.deepcopy(quest_data)
                mirrored["instance_id"] = f"{root_id}_{member_id[-4:]}"
                member.runtime_state.quests.active[mirrored["instance_id"]] = mirrored
                target_session = self._find_online_session_by_player_id(member_id)
                if target_session is not None:
                    events.append(self._event("text", target_session.session_id, f"Party quest shared: {mirrored.get('title', 'Quest')}"))
                    events.append(self._event("quests", target_session.session_id, self._build_quests_payload(target_session.session_id)))
        return events

    def sync_party_quest_completion(self, actor: Any, completed_quest_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return []
        if str(self.party_policy_value("shared_quest_policy", "leader_driven")).strip().lower() != "mirror_all":
            return []

        actor_id = str(getattr(actor, "obj_id", ""))
        party = self._party_for_player_id(actor_id)
        if party is None:
            return []
        root_id = str(completed_quest_data.get("party_shared_root_id", completed_quest_data.get("instance_id", ""))).strip()
        if root_id == "":
            return []

        events: List[Dict[str, Any]] = []
        for member_id in party.member_player_ids:
            if member_id == actor_id:
                continue
            member = self.world.players.get(member_id)
            if member is None:
                continue
            mirrored_id = ""
            for candidate_id, candidate_data in (member.runtime_state.quests.active.items() if member.runtime_state.quests is not None else []):
                if not isinstance(candidate_data, dict):
                    continue
                if str(candidate_data.get("party_shared_root_id", "")) == root_id:
                    mirrored_id = candidate_id
                    break
            if mirrored_id == "":
                continue
            mirrored = member.runtime_state.quests.active.pop(mirrored_id)
            mirrored["state"] = "completed"
            member.runtime_state.quests.completed[mirrored_id] = mirrored
            target_session = self._find_online_session_by_player_id(member_id)
            if target_session is not None:
                events.append(self._event("text", target_session.session_id, f"Party quest completed: {mirrored.get('title', 'Quest')}"))
                events.append(self._event("quests", target_session.session_id, self._build_quests_payload(target_session.session_id)))
        return events

    def _pending_invitees_for_party(self, party_id: str) -> List[str]:
        invited: List[str] = []
        for player_id, invited_party_id in self.pending_party_invites.items():
            if invited_party_id == party_id:
                invited.append(str(player_id))
        return sorted(set(invited))

    def _try_handle_party_command(self, session_id: str, text: str) -> tuple[bool, List[Dict[str, Any]]]:
        normalized = str(text).strip()
        lowered = normalized.lower()
        if not lowered.startswith("party"):
            return False, []
        if self.feature_profile.resolved_world_mode() != "co_op_party":
            return True, [self._event("text", session_id, "Party commands are enabled only in world mode 'co_op_party'.")]

        session = self.sessions.get(session_id)
        if session is None:
            return True, [self._event("text", session_id, "Unknown session.")]

        player = self.get_player_for_session(session_id)
        if player is None:
            return True, [self._event("text", session_id, "Create a character before using party commands.")]

        player_id = str(session.player_id)
        parts = normalized.split()
        action = parts[1].lower() if len(parts) >= 2 else "status"
        party = self._party_for_player_id(player_id)
        events: List[Dict[str, Any]] = []

        if action in {"status", "list"}:
            events.append(self._event("party_state", session_id, self.build_party_state_payload(session_id)))
            if party is None:
                events.append(self._event("text", session_id, "You are not currently in a party."))
            else:
                events.append(
                    self._event(
                        "text",
                        session_id,
                        "Party members: %s"
                        % ", ".join(self._display_name_for_player_id(member_id) for member_id in party.member_player_ids),
                    )
                )
            return True, events

        if action == "invite":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party invite <player-name>")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if target_player_id == player_id:
                return True, [self._event("text", session_id, "You cannot invite yourself.")]
            target_session = self._find_online_session_by_player_id(target_player_id)
            if target_session is None and not self.party_offline_invites_supported():
                return True, [self._event("text", session_id, "Offline party invites are disabled by server policy.")]
            target_party = self._party_for_player_id(target_player_id)
            if target_party is not None:
                return True, [self._event("text", session_id, "That player is already in a party.")]
            party = self._ensure_party_for_leader(player_id)
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the party leader can invite players.")]
            existing_invite_party_id = self.pending_party_invites.get(target_player_id, "")
            if existing_invite_party_id == party.party_id:
                return True, [self._event("text", session_id, f"{self._display_name_for_player_id(target_player_id)} already has a pending invite from your party.")]
            prior_party = self.parties.get(existing_invite_party_id) if existing_invite_party_id else None
            self.pending_party_invites[target_player_id] = party.party_id
            actor_name = self._display_name_for_player_id(player_id)
            target_name_display = self._display_name_for_player_id(target_player_id)
            if prior_party is not None and prior_party.party_id != party.party_id:
                prior_leader_name = self._display_name_for_player_id(prior_party.leader_player_id)
                events.append(
                    self._event(
                        "text",
                        session_id,
                        f"Invited {target_name_display} to the party. Replaced their pending invite from {prior_leader_name}.",
                    )
                )
            else:
                events.append(self._event("text", session_id, f"Invited {target_name_display} to the party."))
            if target_session is not None:
                if prior_party is not None and prior_party.party_id != party.party_id:
                    prior_leader_name = self._display_name_for_player_id(prior_party.leader_player_id)
                    events.append(
                        self._event(
                            "text",
                            target_session.session_id,
                            f"{actor_name} invited you to join their party, replacing your pending invite from {prior_leader_name}. Use: party join",
                        )
                    )
                else:
                    events.append(self._event("text", target_session.session_id, f"{actor_name} invited you to join their party. Use: party join"))
            if prior_party is not None and prior_party.party_id != party.party_id:
                prior_leader_session = self._find_online_session_by_player_id(prior_party.leader_player_id)
                if prior_leader_session is not None and prior_leader_session.session_id != session_id:
                    events.append(
                        self._event(
                            "text",
                            prior_leader_session.session_id,
                            f"Your pending invite for {target_name_display} was replaced by {actor_name}'s party invite.",
                        )
                    )
            sync_player_ids = list(set(party.member_player_ids + [target_player_id]))
            if prior_party is not None and prior_party.party_id != party.party_id:
                sync_player_ids.extend(prior_party.member_player_ids)
            events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            return True, events

        if action == "decline":
            pending_party_id = self.pending_party_invites.get(player_id, "")
            if pending_party_id == "":
                return True, [self._event("text", session_id, "You do not have a pending party invite.")]
            pending_party = self.parties.get(pending_party_id)
            self.pending_party_invites.pop(player_id, None)
            events.append(self._event("text", session_id, "Party invite declined."))
            if pending_party is not None:
                leader_session = self._find_online_session_by_player_id(pending_party.leader_player_id)
                if leader_session is not None:
                    events.append(
                        self._event(
                            "text",
                            leader_session.session_id,
                            f"{self._display_name_for_player_id(player_id)} declined your party invite.",
                        )
                    )
                sync_player_ids = list(set(pending_party.member_player_ids + [player_id]))
                events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            else:
                events.extend(self._party_sync_events_for_player_ids([player_id]))
            return True, events

        if action == "cancel":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party cancel <player-name>")]
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can cancel invitations.")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if self.pending_party_invites.get(target_player_id, "") != party.party_id:
                return True, [self._event("text", session_id, "That player does not have a pending invite from your party.")]
            self.pending_party_invites.pop(target_player_id, None)
            events.append(
                self._event(
                    "text",
                    session_id,
                    f"Cancelled invite for {self._display_name_for_player_id(target_player_id)}.",
                )
            )
            target_session = self._find_online_session_by_player_id(target_player_id)
            if target_session is not None:
                events.append(
                    self._event(
                        "text",
                        target_session.session_id,
                        f"{self._display_name_for_player_id(player_id)} cancelled your party invite.",
                    )
                )
            sync_player_ids = list(set(party.member_player_ids + [target_player_id]))
            events.extend(self._party_sync_events_for_player_ids(sync_player_ids))
            return True, events

        if action == "join":
            pending_party_id = self.pending_party_invites.get(player_id, "")
            if pending_party_id == "":
                return True, [self._event("text", session_id, "You do not have a pending party invite.")]
            if party is not None:
                return True, [self._event("text", session_id, "Leave your current party before joining another one.")]
            invited_party = self.parties.get(pending_party_id)
            if invited_party is None:
                self.pending_party_invites.pop(player_id, None)
                return True, [self._event("text", session_id, "That party invite is no longer valid.")]
            invited_party.member_player_ids.append(player_id)
            self.player_party_membership[player_id] = invited_party.party_id
            self.pending_party_invites.pop(player_id, None)
            leader_name = self._display_name_for_player_id(invited_party.leader_player_id)
            events.append(self._event("text", session_id, f"You joined {leader_name}'s party."))
            leader_session = self._find_online_session_by_player_id(invited_party.leader_player_id)
            if leader_session is not None:
                events.append(self._event("text", leader_session.session_id, f"{self._display_name_for_player_id(player_id)} joined your party."))
            events.extend(self._party_sync_events_for_player_ids(list(invited_party.member_player_ids)))
            return True, events

        if action == "leave":
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            prior_members = list(party.member_player_ids)
            party.member_player_ids = [member_id for member_id in party.member_player_ids if member_id != player_id]
            self.player_party_membership.pop(player_id, None)
            self.pending_party_invites.pop(player_id, None)
            if not party.member_player_ids:
                self.parties.pop(party.party_id, None)
            elif party.leader_player_id == player_id:
                party.leader_player_id = party.member_player_ids[0]
            events.append(self._event("text", session_id, "You left the party."))
            if party is not None and party.party_id in self.parties:
                leader_session = self._find_online_session_by_player_id(party.leader_player_id)
                if leader_session is not None and leader_session.session_id != session_id:
                    events.append(self._event("text", leader_session.session_id, f"{self._display_name_for_player_id(player_id)} left the party."))
            events.extend(self._party_sync_events_for_player_ids(prior_members))
            return True, events

        if action == "leader":
            if len(parts) < 3:
                return True, [self._event("text", session_id, "Usage: party leader <player-name>")]
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can transfer leadership.")]
            target_name = normalized.split(None, 2)[2]
            target_player_id, error = self._find_player_id_by_name(target_name)
            if error:
                return True, [self._event("text", session_id, error)]
            if target_player_id not in party.member_player_ids:
                return True, [self._event("text", session_id, "That player is not in your party.")]
            party.leader_player_id = target_player_id
            events.append(self._event("text", session_id, f"Party leadership transferred to {self._display_name_for_player_id(target_player_id)}."))
            events.extend(self._party_sync_events_for_player_ids(list(party.member_player_ids)))
            return True, events

        if action == "disband":
            if party is None:
                return True, [self._event("text", session_id, "You are not currently in a party.")]
            if party.leader_player_id != player_id:
                return True, [self._event("text", session_id, "Only the current party leader can disband the party.")]
            member_ids = list(party.member_player_ids)
            for member_id in member_ids:
                self.player_party_membership.pop(member_id, None)
                self.pending_party_invites.pop(member_id, None)
            self.parties.pop(party.party_id, None)
            for member_id, invited_party_id in list(self.pending_party_invites.items()):
                if invited_party_id == party.party_id:
                    self.pending_party_invites.pop(member_id, None)
            events.append(self._event("text", session_id, "Party disbanded."))
            events.extend(self._party_sync_events_for_player_ids(member_ids))
            return True, events

        return True, [self._event("text", session_id, "Unknown party command. Use: party status|invite|join|decline|cancel|leave|leader|disband")]

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

    def _flush_background_batch(self, session_id: str) -> List[Dict[str, Any]]:
        """Drain accumulated background events, optionally coalescing text payloads."""
        if not self._background_event_batch:
            return []
        if not self._background_batch_enabled:
            out = list(self._background_event_batch)
            self._background_event_batch.clear()
            return out
        # Coalesce consecutive text events for the same session into one payload
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

    def tick(self, session_id: str, dt: Optional[float] = None) -> List[Dict[str, Any]]:
        self._sync_providers_with_profile()
        if not self._world_mode_tick_enabled():
            return []
        if dt is None or self.deterministic_test_mode:
            dt = self.tick_dt

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
            for msg in player.update(time.time(), dt):
                if self._is_combat_adjacent_message(msg):
                    continue
                # Player regen/effect messages are player-facing — emit direct.
                events.append(self._event("text", session_id, msg))

        # World-effects tick (blight, fields): background — batch.
        for ev in self.world_effects_provider.tick(self, session_id):
            self._background_event_batch.append(ev)

        return events

    def _sync_providers_with_profile(self) -> None:
        weather_mode = str(self.feature_profile.weather_mode).strip().lower()
        if weather_mode != getattr(self.weather_provider, "mode", "builtin"):
            self.weather_provider = self._resolve_weather_provider()
        effects_mode = self._effective_world_effects_mode()
        if effects_mode != getattr(self.world_effects_provider, "mode", "builtin"):
            self.world_effects_provider = self._resolve_world_effects_provider(effects_mode)

    def _effective_world_effects_mode(self) -> str:
        return str(getattr(self.feature_profile, "world_effects_mode", "enabled")).strip().lower()

    def _resolve_weather_provider(self) -> Any:
        mode = str(self.feature_profile.weather_mode).strip().lower()
        if mode == "disabled":
            return DisabledWeatherProvider()
        if mode == "custom":
            provider_id = self._configured_custom_provider_id("weather")
            if provider_id and provider_id in self.custom_weather_providers:
                return self.custom_weather_providers[provider_id]
            if provider_id:
                self.add_boot_warning(
                    code="weather.provider.not_found",
                    message=f"Weather provider id '{provider_id}' was configured but not found. Running no-op provider.",
                    source="weather",
                )
                return CustomWeatherProvider()
            elif self.custom_weather_providers:
                first_provider_id = sorted(self.custom_weather_providers.keys())[0]
                return self.custom_weather_providers[first_provider_id]
            self.add_boot_warning(
                code="weather.provider.missing",
                message="Weather provider mode 'custom' is configured but no custom provider is installed. Running no-op provider.",
                source="weather",
            )
            return CustomWeatherProvider()
        return BuiltinWeatherProvider()

    def _resolve_world_effects_provider(self, mode_override: str | None = None) -> Any:
        mode = str(mode_override or self._effective_world_effects_mode()).strip().lower()
        if mode == "disabled":
            return DisabledWorldEffectsProvider()
        if mode == "custom":
            provider_id = self._configured_custom_provider_id("world_effects")
            if provider_id and provider_id in self.custom_world_effects_providers:
                return self.custom_world_effects_providers[provider_id]
            if provider_id:
                self.add_boot_warning(
                    code="world_effects.provider.not_found",
                    message=f"World-effects provider id '{provider_id}' was configured but not found. Running no-op provider.",
                    source="world_effects",
                )
                return CustomWorldEffectsProvider()
            elif self.custom_world_effects_providers:
                first_provider_id = sorted(self.custom_world_effects_providers.keys())[0]
                return self.custom_world_effects_providers[first_provider_id]
            self.add_boot_warning(
                code="world_effects.provider.missing",
                message="World-effects provider mode 'custom' is configured but no custom provider is installed. Running no-op provider.",
                source="world_effects",
            )
            return CustomWorldEffectsProvider()
        return BuiltinWorldEffectsProvider()

    def _configured_custom_provider_id(self, system_key: str) -> str:
        raw = getattr(self.feature_profile, "raw", {})
        if not isinstance(raw, dict):
            return ""
        node = raw.get(system_key, {})
        if not isinstance(node, dict):
            return ""
        return str(node.get("provider_id", "")).strip()

    def register_weather_provider(self, provider_id: str, provider: Any) -> None:
        pid = str(provider_id).strip()
        if not pid:
            return
        setattr(provider, "mode", "custom")
        setattr(provider, "provider_id", pid)
        self.custom_weather_providers[pid] = provider
        if str(self.feature_profile.weather_mode).strip().lower() == "custom":
            configured = self._configured_custom_provider_id("weather")
            if configured == "" or configured == pid:
                self.weather_provider = provider
        self._sync_providers_with_profile()

    def register_world_effects_provider(self, provider_id: str, provider: Any) -> None:
        pid = str(provider_id).strip()
        if not pid:
            return
        setattr(provider, "mode", "custom")
        setattr(provider, "provider_id", pid)
        self.custom_world_effects_providers[pid] = provider
        if str(self.feature_profile.world_effects_mode).strip().lower() == "custom":
            configured = self._configured_custom_provider_id("world_effects")
            if configured == "" or configured == pid:
                self.world_effects_provider = provider
        self._sync_providers_with_profile()

    def _tick_world_effects_builtin(self, session_id: str) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        field_delta_maps: Dict[str, Dict[str, float]] = {}
        for field_id, field in self.fields.items():
            field_deltas = field.tick()
            if not field_deltas:
                continue
            field_delta_maps[field_id] = {delta.cell_id: delta.value for delta in field_deltas}
            for delta in field_deltas:
                persisted_cell_id = f"{field_id}|{delta.cell_id}"
                self.persistence.queue_world_cell_upsert(
                    persisted_cell_id,
                    {"field_id": field_id, "value": delta.value, "tick": field.tick_index},
                )
        self._apply_field_interactions(field_delta_maps)

        for field_id, delta_map in field_delta_maps.items():
            if not delta_map:
                continue
            field = self.fields[field_id]
            events.append(
                self._event(
                    "world_state",
                    session_id,
                    {
                        "system": "world_effects",
                        "field_id": field_id,
                        "polarity": self.field_polarities.get(field_id, self._classify_polarity(field_id)),
                        "tick": field.tick_index,
                        "cells": [
                            {"cell_id": cell_id, "value": value, "intensity": value}
                            for cell_id, value in sorted(delta_map.items())
                        ],
                    },
                )
            )
        return events

    def execute_command(self, session_id: str, text: str) -> List[Dict[str, Any]]:
        if session_id not in self.sessions:
            return [self._event("error", session_id, f"Unknown session '{session_id}'")]

        events: List[Dict[str, Any]] = [self._event("command", session_id, text)]
        mode_blocked, mode_reason = self._world_mode_command_blocked(session_id)
        if mode_blocked:
            events.append(self._event("text", session_id, mode_reason))
            return events
        shard_block_reason = self.shard_gameplay_block_reason()
        if shard_block_reason:
            events.append(self._event("text", session_id, shard_block_reason))
            return events

        session_obj = self.sessions[session_id]
        session_player = self.get_player_for_session(session_id)
        if session_player is None:
            created_handled, created_message, created = self._handle_character_creation_command(session_id, text)
            if created_handled:
                events.append(self._event("text", session_id, created_message))
                if created:
                    opening_guidance = self.build_opening_guidance()
                    if opening_guidance:
                        events.append(self._event("text", session_id, opening_guidance))
                    self.persist_player_snapshot(session_id)
                    events.append(self._event("status", session_id, self._build_status_payload(session_id)))
                    events.append(self._event("nearby", session_id, self._build_nearby_payload(session_id)))
                return events
            events.append(
                self._event(
                    "text",
                    session_id,
                    "No character yet. Use: char create <name>",
                )
            )
            return events

        capability_reason = self.command_processor.content_block_reason(text, self.world)
        if capability_reason:
            events.append(self._event("text", session_id, capability_reason))
            return events

        party_handled, party_events = self._try_handle_party_command(session_id, text)
        if party_handled:
            events.extend(party_events)
            return events
        finite_handled, finite_events = self._try_handle_finite_adventure_command(session_id, text)
        if finite_handled:
            events.extend(finite_events)
            return events

        pre_active_quest_ids = set(session_player.runtime_state.quests.active) if session_player.runtime_state.quests is not None else set()
        pre_quest_signature = self._quest_state_signature(session_player)

        fx_handled, fx_payload = self._try_handle_fx_debug_command(text)
        if fx_handled:
            events.append(self._event("text", session_id, fx_payload))
        else:
            rules_handled, rules_message = self._try_handle_field_rules_command(text)
            if rules_handled:
                events.append(self._event("text", session_id, rules_message))
            else:
                # Field debug commands (blight/field pulse) require the authoring.gm
                # capability when the server profile restricts authoring.
                authoring_mode = str(self.feature_profile.authoring_mode).strip().lower()
                session_caps = getattr(session_obj, "capabilities", [])
                _field_debug_gm_blocked = (
                    authoring_mode != "all"
                    and "authoring.gm" not in session_caps
                )
                handled, message = self._try_handle_field_debug_command(text)
                if handled:
                    if _field_debug_gm_blocked:
                        events.append(self._event("text", session_id, "Field debug commands require GM access on this server."))
                    else:
                        events.append(self._event("text", session_id, message))
                else:
                    raw_command_text = str(text).strip().lower()

                    def _mapped_entitlement_gate(command_text: str) -> str:
                        # Keep explicit command-to-gate mappings for operator-style
                        # commands that may bypass rich transport envelopes.
                        if command_text.startswith("profile apply "):
                            return "operator.profile.apply"
                        if command_text.startswith("effects use "):
                            return "operator.world_effects.manage"
                        return ""

                    def _authz_hook(cmd_data: Dict[str, Any]) -> bool:
                        if self._readonly_command_blocked(cmd_data, raw_command_text):
                            return False
                        if self._combat_command_blocked(cmd_data, raw_command_text):
                            return False
                        caps = cmd_data.get("capabilities", [])
                        session_caps = getattr(session_obj, "capabilities", [])
                        for cap in caps:
                            if cap not in session_caps:
                                return False
                        entitlements = cmd_data.get("entitlements", [])
                        session_entitlements = list(getattr(session_obj, "entitlements", []))
                        for gate_name in entitlements:
                            allowed, _reason = self.entitlement_guard.check(str(gate_name), session_entitlements)
                            if not allowed:
                                return False
                        mapped_gate = _mapped_entitlement_gate(raw_command_text)
                        if mapped_gate:
                            allowed, _reason = self.entitlement_guard.check(mapped_gate, session_entitlements)
                            if not allowed:
                                return False
                        return True

                    context = {
                        "game": self, 
                        "world": self.world, 
                        "command_processor": self.command_processor,
                        "authz_hook": _authz_hook,
                        "player": self.get_player_for_session(session_id),
                        "session_id": session_id
                    }
                    result = self.command_processor.process_input(text, context)
                    if result:
                        events.append(self._event("text", session_id, result))

        post_quest_ids = set(session_player.runtime_state.quests.active) if session_player.runtime_state.quests is not None else set()
        new_quest_ids = sorted(post_quest_ids - pre_active_quest_ids)
        if new_quest_ids:
            events.extend(self.mirror_party_quest_acceptance(session_player, new_quest_ids))
        post_quest_signature = self._quest_state_signature(session_player)
        quest_state_changed = post_quest_signature != pre_quest_signature

        self.persist_player_snapshot(session_id)
        if self._is_status_command(text):
            events.append(self._event("status", session_id, self._build_status_payload(session_id)))
        if self._is_inventory_command(text):
            events.append(self._event("inventory", session_id, self._build_inventory_payload(session_id)))
        if self._is_quest_command(text) or quest_state_changed:
            events.append(self._event("quests", session_id, self._build_quests_payload(session_id)))
        if self._is_nearby_command(text):
            events.append(self._event("nearby", session_id, self._build_nearby_payload(session_id)))
        if self.feature_profile.resolved_world_mode() == "finite_adventure":
            events.append(self._event("finite_adventure_state", session_id, self.build_finite_adventure_state_payload(session_id)))
            events.append(self._event("finite_adventure_summary", session_id, self.build_finite_adventure_summary_payload(session_id)))
        events.extend(self.tick(session_id))
        # M3: flush batched background events (world tick, weather, effects) as one coalesced payload.
        events.extend(self._flush_background_batch(session_id))

        if getattr(self, "pending_broadcasts", None):
            events.extend(self.pending_broadcasts)
            self.pending_broadcasts = []

        return events

    def _readonly_command_blocked(self, cmd_data: Dict[str, Any], raw_command_text: str = "") -> bool:
        readonly_archive_mode = self.feature_profile.resolved_world_mode() == "readonly_archive"
        readonly_mutation_mode = not self.feature_profile.world_mutation_allowed()
        if not readonly_archive_mode and not readonly_mutation_mode:
            return False
        first_token = raw_command_text.split()[0] if raw_command_text.strip() else ""
        cmd_name = str(cmd_data.get("name", "")).strip().lower()
        cmd_category = str(cmd_data.get("category", "")).strip().lower()
        if cmd_name.startswith("@"):
            return True
        if cmd_category == "combat":
            return True
        # Static-world policy: disallow known gameplay verbs that mutate
        # rooms/world entities or persistent progression state.
        blocked_names = {
            "take",
            "drop",
            "give",
            "put",
            "use",
            "equip",
            "unequip",
            "buy",
            "sell",
            "craft",
            "repair",
            "consume",
            "drink",
            "eat",
            "cast",
            "attack",
            "kill",
            "flee",
            "accept",
            "complete",
            "abandon",
            "turnin",
            "lock",
            "unlock",
            "pick",
            "open",
            "close",
            "dig",
            "edit",
            "build",
            "spawn",
            "summon",
        }
        return cmd_name in blocked_names or first_token in blocked_names

    def _combat_command_blocked(self, cmd_data: Dict[str, Any], raw_command_text: str = "") -> bool:
        if str(self.feature_profile.combat_mode).strip().lower() != "disabled":
            return False
        first_token = raw_command_text.split()[0] if raw_command_text.strip() else ""
        cmd_name = str(cmd_data.get("name", "")).strip().lower()
        cmd_category = str(cmd_data.get("category", "")).strip().lower()
        if cmd_category == "combat":
            return True
        blocked_names = {
            "attack",
            "kill",
            "flee",
            "cast",
            "shoot",
            "strike",
            "stab",
            "slash",
            "smite",
        }
        return cmd_name in blocked_names or first_token in blocked_names

    def execute_command_envelope(self, envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
        envelope = dict(envelope)
        envelope.setdefault("client_capabilities", {})
        valid, reason = validate_client_command_envelope(envelope)
        session_id = envelope.get("session_id", "unknown")
        if not valid:
            return [self._event("error", session_id, f"Invalid command envelope: {reason}")]
        command_text = envelope["command_text"]
        return self.execute_command(session_id, command_text)

    def _init_field_state(self) -> None:
        existing_cells = self.persistence.load_world_cells()
        grouped_states: Dict[str, Dict[str, float]] = {}
        if existing_cells:
            for raw_cell_id, state in existing_cells.items():
                if "|" in raw_cell_id:
                    field_id, cell_id = raw_cell_id.split("|", 1)
                else:
                    field_id, cell_id = "blight", raw_cell_id
                grouped_states.setdefault(field_id, {})
                grouped_states[field_id][cell_id] = float(state.get("value", state.get("intensity", 0.0)))
            for field_id, states in grouped_states.items():
                heartbeat = self._ensure_field(field_id)
                heartbeat.load_cells(states)
            return
        default_field = self._ensure_field("blight")
        center_x = default_field.width // 2
        center_y = default_field.height // 2
        default_field.seed_cell(center_x, center_y, value=1.0)

    def _try_handle_field_debug_command(self, text: str) -> tuple[bool, str]:
        command = text.strip()
        if command == "":
            return False, ""

        parts = command.split()
        if len(parts) < 2:
            return False, ""
        prefix = parts[0].lower()
        if prefix not in {"blight", "field"} or parts[1].lower() != "pulse":
            return False, ""
        if not self.feature_profile.world_mutation_allowed():
            return True, "World mutation is disabled by server profile."

        field_id = self.default_field_id
        idx = 2
        if prefix == "field" and len(parts) >= 3 and not parts[2].lstrip("-").isdigit():
            field_id = parts[2].lower()
            idx = 3
        heartbeat = self._ensure_field(field_id)
        polarity = self.field_polarities.get(field_id, self._classify_polarity(field_id))

        x = heartbeat.width // 2
        y = heartbeat.height // 2
        value = 1.0

        try:
            if len(parts) >= idx + 2:
                x = int(parts[idx])
                y = int(parts[idx + 1])
            if len(parts) >= idx + 3:
                value = float(parts[idx + 2])
        except ValueError:
            return True, "Usage: blight pulse [x y [intensity]] OR field pulse [field_id] [x y [value]]"

        if x < 0 or y < 0 or x >= heartbeat.width or y >= heartbeat.height:
            return True, f"Field pulse rejected: coordinates out of bounds (0-{heartbeat.width - 1}, 0-{heartbeat.height - 1})."

        clamped_value = max(0.0, min(1.0, value))
        heartbeat.seed_cell(x, y, clamped_value)
        self.default_field_id = field_id
        self.default_field_polarity = polarity
        self.field_polarities[field_id] = polarity
        return True, f"Field pulse seeded: {field_id} at {x}:{y} (value {clamped_value:.2f}, {polarity})."

    def _try_handle_field_rules_command(self, text: str) -> tuple[bool, str]:
        normalized = text.strip().lower()
        if normalized not in {"field rules", "field rule", "field config"}:
            return False, ""
        fallback = float(
            self.field_interaction_profiles.get("positive_suppresses_negative", {}).get("coefficient", 0.0)
        )
        payload = {
            "fallback_positive_suppresses_negative": round(fallback, 4),
            "pairwise_rules": self.field_interaction_rules,
        }
        return True, json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    def _ensure_field(self, field_id: str) -> WorldEffectsHeartbeat:
        if field_id not in self.fields:
            self.fields[field_id] = WorldEffectsHeartbeat()
            self.field_polarities[field_id] = self._classify_polarity(field_id)
        return self.fields[field_id]

    def _apply_field_interactions(self, field_delta_maps: Dict[str, Dict[str, float]]) -> None:
        fallback_coefficient = float(
            self.field_interaction_profiles.get("positive_suppresses_negative", {}).get("coefficient", 0.0)
        )

        source_snapshots = {fid: hb.snapshot() for fid, hb in self.fields.items()}
        for target_id, target_hb in self.fields.items():
            target_snapshot = target_hb.snapshot()
            if not target_snapshot:
                continue
            multipliers: Dict[str, float] = {}
            for cell_id, target_value in target_snapshot.items():
                if target_value <= 0.0:
                    continue
                strongest_effect = 0.0
                for source_id, source_map in source_snapshots.items():
                    source_value = float(source_map.get(cell_id, 0.0))
                    if source_value <= 0.0 or source_id == target_id:
                        continue
                    coefficient = self._interaction_coefficient(source_id, target_id, fallback_coefficient)
                    if coefficient <= 0.0:
                        continue
                    strongest_effect = max(strongest_effect, coefficient * source_value)
                if strongest_effect <= 0.0:
                    continue
                damp_factor = max(0.0, 1.0 - strongest_effect)
                if damp_factor < 1.0:
                    multipliers[cell_id] = damp_factor

            if not multipliers:
                continue
            interaction_deltas = target_hb.apply_multipliers(multipliers)
            if not interaction_deltas:
                continue
            field_delta_maps.setdefault(target_id, {})
            for delta in interaction_deltas:
                field_delta_maps[target_id][delta.cell_id] = delta.value
                persisted_cell_id = f"{target_id}|{delta.cell_id}"
                self.persistence.queue_world_cell_upsert(
                    persisted_cell_id,
                    {"field_id": target_id, "value": delta.value, "tick": target_hb.tick_index},
                )

    def _interaction_coefficient(self, source_id: str, target_id: str, fallback: float) -> float:
        explicit = self.field_interaction_rules.get(source_id, {}).get(target_id)
        if explicit is not None:
            return max(0.0, float(explicit))
        source_pol = self.field_polarities.get(source_id, self._classify_polarity(source_id))
        target_pol = self.field_polarities.get(target_id, self._classify_polarity(target_id))
        if source_pol == "positive" and target_pol == "negative":
            return max(0.0, fallback)
        return 0.0

    def _classify_polarity(self, field_id: str) -> str:
        if field_id in {"sanctity", "harmony", "vitality", "hope"}:
            return "positive"
        if field_id in {"fog", "entropy", "wild"}:
            return "neutral"
        return "negative"

    def _is_status_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"status", "stat", "st"}

    def _try_handle_fx_debug_command(self, text: str) -> tuple[bool, Any]:
        """
        Debug command for client-side atmospheric text rendering:
        fx <shiver|bleed|rot> <severity 0..1> [duration_ms] [message...]
        """
        parts = text.strip().split()
        if not parts or parts[0].lower() != "fx":
            return False, ""
        if len(parts) < 3:
            return True, "Usage: fx <shiver|bleed|rot> <severity 0..1> [duration_ms] [message]"

        effect_type = parts[1].lower()
        if effect_type not in {"shiver", "bleed", "rot"}:
            return True, "Usage: fx <shiver|bleed|rot> <severity 0..1> [duration_ms] [message]"

        try:
            severity = float(parts[2])
        except ValueError:
            return True, "Usage: fx <shiver|bleed|rot> <severity 0..1> [duration_ms] [message]"
        severity = max(0.0, min(1.0, severity))

        duration_ms = 1200
        message_start = 3
        if len(parts) >= 4:
            try:
                duration_ms = int(parts[3])
                message_start = 4
            except ValueError:
                message_start = 3
        duration_ms = max(100, min(60000, duration_ms))

        msg = " ".join(parts[message_start:]).strip()
        if msg == "":
            msg = f"Atmospheric effect sample: {effect_type} (severity {severity:.2f})"

        return True, {
            "text": msg,
            "fx": {
                "effect_type": effect_type,
                "severity": severity,
                "duration_ms": duration_ms,
            },
        }

    def _build_status_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player:
            payload = {
                "name": "Unknown",
                "health": {"current": 0, "max": 0},
                "alive": False,
                "effects": [],
            }
            if self.world.has_capability("magic"):
                payload["mana"] = {"current": 0, "max": 0}
            return payload

        effect_names: List[str] = []
        for effect in getattr(player, "active_effects", []):
            # active_effects entries are plain dicts (see GameObject.apply_effect),
            # not objects, so the name must be read via mapping access.
            effect_name = effect.get("name") if isinstance(effect, dict) else getattr(effect, "name", None)
            if effect_name:
                effect_names.append(str(effect_name))
            else:
                effect_names.append(str(effect))

        payload = {
            "name": str(getattr(player, "name", "Player")),
            "health": {
                "current": int(getattr(player, "health", 0)),
                "max": int(getattr(player, "max_health", 0)),
            },
            "alive": bool(getattr(player, "is_alive", False)),
            "effects": effect_names,
        }
        if self.world.uses_progression() and player.runtime_state.progression is not None:
            payload["level"] = int(player.runtime_state.progression.level)
            payload["experience"] = int(player.runtime_state.progression.experience)
        if self.world.has_capability("magic") and player.runtime_state.magic is not None:
            payload["mana"] = {
                "current": int(player.runtime_state.magic.mana),
                "max": int(player.runtime_state.magic.max_mana),
            }
        return payload

    def _is_inventory_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"inventory", "inv", "i"}

    def _build_inventory_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player or not hasattr(player, "inventory"):
            return {
                "items": [],
                "slots_used": 0,
                "slots_max": 0,
                "total_weight": 0.0,
                "max_weight": 0.0,
            }

        inventory = player.inventory
        items: List[Dict[str, Any]] = []
        for idx, slot in enumerate(inventory.slots):
            if not slot.item:
                continue
            item_weight = float(getattr(slot.item, "weight", 0.0))
            items.append(
                {
                    "slot_index": idx,
                    "item_id": str(getattr(slot.item, "obj_id", "unknown")),
                    "name": str(getattr(slot.item, "name", "Unknown Item")),
                    "quantity": int(getattr(slot, "quantity", 1)),
                    "stackable": bool(getattr(slot.item, "stackable", False)),
                    "weight_each": item_weight,
                    "weight_total": item_weight * int(getattr(slot, "quantity", 1)),
                }
            )

        return {
            "items": items,
            "slots_used": len(items),
            "slots_max": int(getattr(inventory, "max_slots", len(inventory.slots))),
            "total_weight": float(inventory.get_total_weight()),
            "max_weight": float(getattr(inventory, "max_weight", 0.0)),
        }

    def _is_quest_command(self, text: str) -> bool:
        parts = text.strip().lower().split()
        if not parts:
            return False
        return parts[0] in {"journal", "quests", "log", "j"}

    def _build_quests_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        if not player or player.runtime_state.quests is None:
            return {"active": [], "completed": [], "archived": []}

        active_items = self._normalize_quest_entries(player.runtime_state.quests.active, include_states={"active", "ready_to_complete"})
        completed_items = self._normalize_quest_entries(player.runtime_state.quests.completed, include_states=None)
        archived_items = self._normalize_quest_entries(player.runtime_state.quests.archived, include_states=None)
        return {
            "active": active_items,
            "completed": completed_items,
            "archived": archived_items,
        }

    def _quest_state_signature(self, player: Any) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        if player is None or player.runtime_state.quests is None:
            return ((), (), ())
        active_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.active.keys()))
        completed_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.completed.keys()))
        archived_ids = tuple(sorted(str(key) for key in player.runtime_state.quests.archived.keys()))
        return (active_ids, completed_ids, archived_ids)

    def _is_nearby_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        if normalized in {"nearby", "scan", "who"}:
            return True
        parts = normalized.split()
        if not parts:
            return False
        # Nearby payloads are used by the client room panel. Emit them for both
        # explicit observation commands and movement commands so navigation updates
        # the UI without requiring a follow-up "look".
        if parts[0] in {"look", "l", "go", "north", "south", "east", "west", "up", "down", "n", "s", "e", "w", "u", "d"}:
            return True
        return False

    def _build_nearby_payload(self, session_id: str) -> Dict[str, Any]:
        player = self.get_player_for_session(session_id)
        # Use the session player's location when available so that each session
        # sees its own room rather than a process-global accessor
        # (world.current_region_id is backed by world.player which is None in
        # headless multi-session mode).
        if player:
            region_id = str(getattr(player, "current_region_id", "") or "")
            room_id = str(getattr(player, "current_room_id", "") or "")
        else:
            region_id = str(self.world.current_region_id or "")
            room_id = str(self.world.current_room_id or "")

        region = self.world.get_region(region_id) if region_id else None
        room = region.get_room(room_id) if region and room_id else None
        if not room:
            return {
                "location": {"region_id": "", "region_name": "Unknown", "room_id": "", "room_name": "Unknown"},
                "exits": [],
                "npcs": [],
                "items": [],
                "interactions": [],
            }

        exits = sorted([str(direction) for direction in room.exits.keys()])
        npcs = sorted(
            [
                {
                    "npc_id": str(getattr(npc, "obj_id", "unknown")),
                    "name": str(getattr(npc, "name", "Unknown NPC")),
                    "faction": str(getattr(npc, "faction", "unknown")),
                    "hostile": (
                        self.feature_profile.combat_mode != "disabled"
                        and str(getattr(npc, "faction", "")) == "hostile"
                    ),
                }
                for npc in self.world.get_npcs_in_room(region_id, room_id)
            ],
            key=lambda n: str(n.get("name", "")),
        )
        items = sorted(
            [
                {
                    "item_id": str(getattr(item, "obj_id", "unknown")),
                    "name": str(getattr(item, "name", "Unknown Item")),
                    "portable": bool(getattr(item, "portable", True)),
                }
                for item in self.world.get_items_in_room(region_id, room_id)
            ],
            key=lambda i: str(i.get("name", "")),
        )

        interactions: List[str] = []
        for direction in exits[:4]:
            interactions.append(f"go {direction}")
        for npc in npcs[:3]:
            interactions.append(f"talk {npc.get('name', 'npc')}")
        for item in items[:3]:
            interactions.append(f"take {item.get('name', 'item')}")

        return {
            "location": {
                "region_id": region_id,
                "region_name": str(getattr(region, "name", "Unknown Region")),
                "room_id": room_id,
                "room_name": str(getattr(room, "name", "Unknown Room")),
            },
            "exits": exits,
            "npcs": npcs,
            "items": items,
            "interactions": interactions,
        }

    def _normalize_quest_entries(self, quest_map: Any, include_states: Optional[set[str]]) -> List[Dict[str, Any]]:
        if not isinstance(quest_map, dict):
            return []
        entries: List[Dict[str, Any]] = []
        for quest_id, raw in quest_map.items():
            if not isinstance(raw, dict):
                continue
            state = str(raw.get("state", "unknown"))
            if include_states is not None and state not in include_states:
                continue
            entries.append(
                {
                    "quest_id": str(quest_id),
                    "title": str(raw.get("title", "Unnamed Quest")),
                    "state": state,
                    "current_stage_index": int(raw.get("current_stage_index", 0)),
                }
            )
        entries.sort(key=lambda q: q.get("title", ""))
        return entries

    def _is_combat_adjacent_message(self, message: Any) -> bool:
        if str(self.feature_profile.combat_mode).strip().lower() != "disabled":
            return False
        normalized = str(message).strip().lower()
        if normalized == "":
            return False
        combat_tokens = (
            "attacks",
            "hits",
            "misses",
            "critical hit",
            "combat",
            "damage",
            "bleed",
            "kills",
            "defeated",
            "slain",
            "you are dead",
            "you died",
        )
        return any(token in normalized for token in combat_tokens)
