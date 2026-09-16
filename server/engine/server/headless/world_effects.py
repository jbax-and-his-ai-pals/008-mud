# engine/server/headless/world_effects.py
"""WorldEffectsMixin: extracted from HeadlessServer (see headless_server.py) as part
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


class WorldEffectsMixin:
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
