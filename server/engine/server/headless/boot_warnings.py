# engine/server/headless/boot_warnings.py
"""BootWarningsMixin: extracted from HeadlessServer (see headless_server.py) as part
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


class BootWarningsMixin:
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
