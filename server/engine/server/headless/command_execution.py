# engine/server/headless/command_execution.py
"""CommandExecutionMixin: extracted from HeadlessServer (see headless_server.py) as part
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
from engine.commands.command_system import (
    CommandProcessor,
    command_failure_message,
    report_command_failure,
)


def _command_name(text: str) -> str:
    """The command word in a line of input, for a report or a refusal."""
    stripped = str(text).strip()
    return stripped.split(maxsplit=1)[0].lower() if stripped else ""

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


class CommandExecutionMixin:
    def execute_command(self, session_id: str, text: str) -> List[Dict[str, Any]]:
        """Run one command for one session, and never let it end the session.

        `CommandProcessor.process_input` already stops a *handler* that raises.
        This is the second boundary: the status, inventory and quest payloads
        built after a command, and the world tick that follows it, read the same
        content and can fail the same way. A player who typed something
        reasonable should get an answer either way -- on a shared server the
        alternative is a broken connection.
        """
        try:
            return self._execute_command(session_id, text)
        except Exception as error:
            report_command_failure(_command_name(text), str(text).split(), error, {"world": self.world})
            events: List[Dict[str, Any]] = [self._event("command", session_id, text)]
            events.append(self._event("error", session_id, command_failure_message(_command_name(text), error)))
            return events

    def _execute_command(self, session_id: str, text: str) -> List[Dict[str, Any]]:
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

        # Headless sessions persist their character snapshot after every
        # command. The desktop save/load commands serialize or replace the
        # entire shared World, so allowing them here would let one session
        # affect every active character. Keep persistence session-scoped.
        command_name = str(text).strip().split(maxsplit=1)[0].lower() if str(text).strip() else ""
        if command_name in {"save", "load"}:
            events.append(
                self._event(
                    "text",
                    session_id,
                    "Character progress is saved automatically on this server. "
                    "Manual save and load are unavailable in a shared world.",
                )
            )
            self.persist_player_snapshot(session_id)
            events.extend(self.tick(session_id))
            events.extend(self._flush_background_batch(session_id))
            if getattr(self, "pending_broadcasts", None):
                events.extend(self.pending_broadcasts)
                self.pending_broadcasts = []
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
                        if self._presentation_mode_blocked(cmd_data, session_obj):
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
                    # The nearby panel is also exposed as a terminal-friendly
                    # observation command. Keep aliases generic: they render
                    # the current room rather than depending on a content verb.
                    if raw_command_text in {"nearby", "scan", "who"}:
                        result = self.world.look(minimal=True, player=session_player)
                    else:
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
        if self._is_combat_command(text):
            # Combat changes vitals more often than a player explicitly asks for
            # status. Keep the client encounter card authoritative after every
            # combat decision instead of leaving it stale until `status`.
            events.append(self._event("status", session_id, self._build_status_payload(session_id)))
            events.append(self._event("combat", session_id, self._build_combat_payload(session_id)))
        if self._is_inventory_command(text) or self._is_attachment_command(text):
            events.append(self._event("inventory", session_id, self._build_inventory_payload(session_id)))
        if self._is_crafting_command(text):
            events.append(self._event("crafting", session_id, self._build_crafting_payload(session_id)))
        if self._is_collection_command(text):
            events.append(self._event("collections", session_id, self._build_collections_payload(session_id)))
        if self._is_discovery_command(text):
            events.append(self._event("discoveries", session_id, self._build_discoveries_payload(session_id)))
        if self._is_relationship_command(text):
            events.append(self._event("relationships", session_id, self._build_relationships_payload(session_id)))
        if self._is_quest_command(text) or quest_state_changed:
            events.append(self._event("quests", session_id, self._build_quests_payload(session_id)))
        if self._is_nearby_command(text):
            events.append(self._event("nearby", session_id, self._build_nearby_payload(session_id)))
        if self.feature_profile.resolved_world_mode() == "finite_adventure" and self.world.has_capability("quests"):
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

    def _presentation_mode_blocked(self, cmd_data: Dict[str, Any], session_obj: Any = None) -> bool:
        """Whether this command is hidden from the session's presentation mode.

        A player-mode session must never reach the `debug` category. Before
        this guard existed, every debug command that did not declare an
        entitlement was reachable by a brand-new level-1 character --
        `level 5`, `setgold 1000`, `sethealth 9999`, and
        `teleport forest forest_edge` all succeeded, because the five commands
        that *did* declare `operator.world.debug` were protected only when a
        server config happened to define that gate, and
        `EntitlementGuard.check()` returns allow for an undefined gate.

        Session-level `presentation_mode` is the authority here rather than the
        entitlement list, because it is the same switch that decides whether
        engine internals are shown at all (docs/design/WORLD_DESIGN.md §2), and
        because it must default to closed for anything claiming to be a player.

        A session in `test` mode is unaffected, which keeps the whole existing
        test suite, the journey lab, and operator tooling working unchanged.
        """
        mode = str(getattr(session_obj, "presentation_mode", "test") or "test").strip().lower()
        if mode != "player":
            return False
        return str(cmd_data.get("category", "")).strip().lower() == "debug"

    def _combat_command_blocked(self, cmd_data: Dict[str, Any], raw_command_text: str = "") -> bool:
        if str(self.feature_profile.combat_mode).strip().lower() != "disabled":
            return False
        first_token = raw_command_text.split()[0] if raw_command_text.strip() else ""
        cmd_name = str(cmd_data.get("name", "")).strip().lower()
        cmd_category = str(cmd_data.get("category", "")).strip().lower()
        if cmd_category == "combat":
            return True
        # "attack"/"kill"/"flee"/"cast" are the engine's own generic combat
        # and magic command names -- "cast" in particular is category
        # "magic", not "combat", but offensive spells route through it.
        # A content set with its own offensive commands under a different
        # category/name extends this via "combat.additional_blocked_command_names".
        blocked_names = {"attack", "kill", "flee", "cast"} | {
            str(n).strip().lower() for n in self.world.ruleset_section("combat").get("additional_blocked_command_names", [])
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
