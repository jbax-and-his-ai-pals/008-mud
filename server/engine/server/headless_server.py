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
from engine.server.headless.models import Session, Party
from engine.server.headless.boot_warnings import BootWarningsMixin
from engine.server.headless.session import SessionMixin
from engine.server.headless.finite_adventure import FiniteAdventureMixin
from engine.server.headless.party import PartyMixin
from engine.server.headless.shard import ShardMixin
from engine.server.headless.lifecycle import LifecycleMixin
from engine.server.headless.world_effects import WorldEffectsMixin
from engine.server.headless.command_execution import CommandExecutionMixin
from engine.server.headless.field_fx import FieldFxMixin
from engine.server.headless.status_payloads import StatusPayloadsMixin


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


class HeadlessServer(
    BootWarningsMixin, SessionMixin, FiniteAdventureMixin, PartyMixin, ShardMixin,
    LifecycleMixin, WorldEffectsMixin, CommandExecutionMixin, FieldFxMixin, StatusPayloadsMixin,
):
    """Minimal authoritative headless runtime that reuses existing world/command systems."""
    def __init__(
        self,
        save_file: str = "server_save.json",
        db_path: Optional[str] = None,
        content_set_path: Optional[str] = None,
        save_directory: Optional[str] = None,
        field_config_path: Optional[str] = None,
        feature_profile: Optional[FeatureProfile] = None,
        starter_items: Optional[List[Dict[str, Any] | str]] = None,
        entitlement_policy: Optional[Dict[str, Any]] = None,
        mods_dir: Optional[str] = None,
        tick_rate_hz: float = 10.0,
        deterministic_test_mode: bool = False,
        require_character_creation: bool = True,
        boot_warning_fail_codes: Optional[List[str]] = None,
        clock: Optional[Clock] = None,
        default_presentation_mode: str = "test",
    ) -> None:
        self.tick_rate_hz = tick_rate_hz
        self.tick_dt = 1.0 / self.tick_rate_hz
        self.deterministic_test_mode = deterministic_test_mode
        resolved_presentation_mode = str(default_presentation_mode or "test").strip().lower()
        self.default_presentation_mode = (
            resolved_presentation_mode if resolved_presentation_mode in {"player", "test"} else "test"
        )
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
        self.content_set: ContentSetDefinition = definition
        self.content_set_path: str = str(definition.manifest_path)
        self.content_root = os.path.abspath(str(definition.content_root))
        if clock is None:
            clock = SimulatedClock() if self.deterministic_test_mode else WallClock()
        self.world = World(
            content_set=self.content_set,
            save_directory=save_directory,
            clock=clock,
        )
        setattr(self.world, "server", self)
        self.world.bootstrap_starter_items = list(starter_items) if starter_items else None
        self.command_processor = CommandProcessor()
        # Client-side display hint (text/icon/hybrid); the server does not
        # render, but `invmode` reads/writes it for parity with GameManager.
        self.inventory_mode = "hybrid"
        self.time_manager = TimeManager(self.world)
        self.weather_manager = WeatherManager(self.world)
        self.crafting_manager = (
            CraftingManager(self.world)
            if self.world.has_capability("crafting")
            else None
        )
        self.boot_warnings: List[str] = []
        self.boot_warning_records: List[Dict[str, str]] = []
        self._boot_warning_keys: set[tuple[str, str, str]] = set()
        self.knowledge_manager = KnowledgeManager(
            self.world,
            warning_sink=self.add_boot_warning,
        )
        self.collection_manager = CollectionManager(self.world)
        self.discovery_manager = DiscoveryManager(self.world)
        # P4 progression spine. The advancement ledger is the player's record
        # of what they have seen and done, and the source of most XP; titles are
        # the identity earned from it; backgrounds are where a character began.
        self.advancement_manager = AdvancementManager(self.world)
        self.title_manager = TitleManager(self.world)
        self.background_manager = BackgroundManager(self.world)
        # P5 dialogue. Content-authored conversation graphs, loaded from
        # `data/dialogue/`. Structural problems (a root that does not exist, a
        # `next_node` pointing at nothing) surface here as boot warnings and, in
        # CI, as content-validation errors.
        self.dialogue_manager = DialogueManager(self.world)
        for manager in (self.advancement_manager, self.title_manager, self.background_manager,
                        self.dialogue_manager):
            for issue in getattr(manager, "issues", []):
                self.add_boot_warning("content", "advancement", str(issue))
        # The world needs these reachable from gameplay code that only has a
        # world or a player (region entry, item pickup, quest completion).
        # `world.server` is what display and progression code uses to find the
        # session's presentation mode and the authored XP curve; tests set it
        # themselves, but nothing on the real path did.
        self.world.advancement_manager = self.advancement_manager
        self.world.title_manager = self.title_manager
        self.world.dialogue_manager = self.dialogue_manager
        self.world.server = self
        self.renderer = _NullRenderer()
        self.input_handler = _NullInputHandler()
        self.current_save_file = save_file
        self.db_path = db_path or os.path.abspath("server_state.sqlite3")
        self.persistence = SqliteStore(self.db_path)
        self.persistence.start_async_writer()
        self.feature_profile_source_path = "injected" if feature_profile is not None else str(definition.feature_profile_path or "")
        self.feature_profile = feature_profile or FeatureProfile.load(self.feature_profile_source_path or None)
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
        # source_field -> {target_field: suppression_coefficient}; content
        # sets provide their own via field_interactions.json's
        # "pairwise_rules" -- the engine ships no default field vocabulary.
        self.field_interaction_rules: Dict[str, Dict[str, float]] = {}
        self.field_interaction_profiles: Dict[str, Dict[str, float]] = {
            "positive_suppresses_negative": {"coefficient": 0.60}
        }
        self.default_field_id = "blight"
        self.default_field_polarity = "negative"
        default_field_config = os.path.join(self.content_root, "world", "field_interactions.json")
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

    def _event(self, event_type: str, session_id: str, payload: Any) -> Dict[str, Any]:
        return build_server_event(event_type, session_id, payload, time.time())

