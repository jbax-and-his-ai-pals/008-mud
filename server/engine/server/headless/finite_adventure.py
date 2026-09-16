# engine/server/headless/finite_adventure.py
"""FiniteAdventureMixin: extracted from HeadlessServer (see headless_server.py) as part
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


class FiniteAdventureMixin:
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
        finite_state = player.runtime_state.quests.finite_adventure if player.runtime_state.quests is not None else None
        if not isinstance(finite_state, dict):
            finite_state = {}
        started_at = finite_state.get("started_at")
        history: List[Dict[str, Any]] = []
        active_campaigns = player.runtime_state.quests.active_campaigns if player.runtime_state.quests is not None else None
        completed_campaigns = player.runtime_state.quests.completed_campaigns if player.runtime_state.quests is not None else None
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
        progression = player.runtime_state.progression
        magic = player.runtime_state.magic
        quests = player.runtime_state.quests
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
            "player_level": int(progression.level) if progression is not None else 0,
            "player_gold": int(player.runtime_state.gold) if player.runtime_state.gold is not None else 0,
            "final_health": int(getattr(player, "health", 0)),
            "max_health": int(getattr(player, "max_health", 0)),
            "final_mana": int(magic.mana) if magic is not None else 0,
            "max_mana": int(magic.max_mana) if magic is not None else 0,
            "quest_log_count": len(quests.active) if quests is not None else 0,
            "completed_quest_count": len(quests.completed) if quests is not None else 0,
            "archived_quest_count": len(quests.archived) if quests is not None else 0,
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
                f"- {self.world.currency_name().capitalize()}: `{summary.get('player_gold', 0)}`",
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
            f"Player {player_name} (level {player_level}) finished with {gold} {self.world.currency_name()}.{duration_text}"
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
        if player.runtime_state.quests is not None:
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
        player.is_alive = True
        if player.runtime_state.magic is not None:
            player.runtime_state.magic.mana = int(player.runtime_state.magic.max_mana)
            player.runtime_state.magic.cooldowns = {}
            player.runtime_state.magic.summons = {}
        if player.runtime_state.combat is not None:
            player.runtime_state.combat.in_combat = False
            player.runtime_state.combat.target = None
            player.runtime_state.combat.targets = set()
        player.combat_messages = []
        player.active_effects = []
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
