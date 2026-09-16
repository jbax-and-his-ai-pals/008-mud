# engine/server/headless/field_fx.py
"""FieldFxMixin: extracted from HeadlessServer (see headless_server.py) as part
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


class FieldFxMixin:
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

        raw_polarities = raw.get("polarities", {})
        if isinstance(raw_polarities, dict):
            for field_id, polarity in raw_polarities.items():
                field_key = str(field_id).strip().lower()
                polarity_value = str(polarity).strip().lower()
                if field_key and polarity_value in {"positive", "neutral", "negative"}:
                    self.field_polarities[field_key] = polarity_value

        default_field_id = raw.get("default_field_id")
        if isinstance(default_field_id, str) and default_field_id.strip():
            self.default_field_id = default_field_id.strip().lower()
            self.default_field_polarity = self.field_polarities.get(
                self.default_field_id, self._classify_polarity(self.default_field_id)
            )

    def _init_field_state(self) -> None:
        existing_cells = self.persistence.load_world_cells()
        grouped_states: Dict[str, Dict[str, float]] = {}
        if existing_cells:
            for raw_cell_id, state in existing_cells.items():
                if "|" in raw_cell_id:
                    field_id, cell_id = raw_cell_id.split("|", 1)
                else:
                    field_id, cell_id = self.default_field_id, raw_cell_id
                grouped_states.setdefault(field_id, {})
                grouped_states[field_id][cell_id] = float(state.get("value", state.get("intensity", 0.0)))
            for field_id, states in grouped_states.items():
                heartbeat = self._ensure_field(field_id)
                heartbeat.load_cells(states)
            return
        if not os.path.exists(self.field_config_path):
            # No ambient-field system configured for this content set (no
            # field_interactions.json) -- don't invent one to seed.
            return
        default_field = self._ensure_field(self.default_field_id)
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
            if field_id not in self.field_polarities:
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
        """Last-resort fallback for a field with no configured polarity.

        Content sets declare real polarities via field_interactions.json's
        "polarities" section (see self.field_polarities); this only fires
        for a field the content set never classified at all, so it stays
        neutral (no suppression effect either direction) rather than
        assuming an unknown field is harmful.
        """
        return "neutral"

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
