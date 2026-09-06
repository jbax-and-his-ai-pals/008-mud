import argparse
import asyncio
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from engine.server import HeadlessServer
from engine.server.feature_profile import FeatureProfile
from engine.server.input_safeguards import InputSafeguards
from engine.server.realtime_assets import RealtimeAssetService
from engine.server.server_config import load_server_config, resolve_server_settings
from engine.server.entitlement import EntitlementGuard
from engine.commands.command_system import get_registered_commands


class JsonLineMudServer:
    def __init__(
        self,
        host: str,
        port: int,
        save_file: str,
        asset_db_path: str = ":memory:",
        content_set_path: str | None = None,
        feature_profile: FeatureProfile | None = None,
        session_default_capabilities: list[str] | None = None,
        session_default_entitlements: list[str] | None = None,
        session_authz_detail_level: str = "full",
        gm_auth_token: str | None = None,
        entitlement_policy: dict[str, Any] | None = None,
        max_command_chars: int = 512,
        max_envelope_bytes: int = 8192,
        command_rate_limit_per_sec: float = 8.0,
        command_burst: int = 16,
        starter_items: list[dict[str, Any] | str] | None = None,
        require_character_creation: bool = False,
        boot_warning_fail_codes: list[str] | None = None,
    ):
        self.host = host
        self.port = port
        self.content_set_path = content_set_path
        self.server = HeadlessServer(
            save_file=save_file,
            db_path=":memory:",
            content_set_path=content_set_path,
            feature_profile=feature_profile,
            starter_items=starter_items,
            require_character_creation=require_character_creation,
            boot_warning_fail_codes=boot_warning_fail_codes,
        )
        self._tcp_server: asyncio.AbstractServer | None = None
        self._session_writers: Dict[str, asyncio.StreamWriter] = {}
        self.assets = RealtimeAssetService(self.server._event, asset_db_path=asset_db_path)
        self.session_default_capabilities = list(session_default_capabilities or [])
        self.session_default_entitlements = list(session_default_entitlements or [])
        authz_level = str(session_authz_detail_level).strip().lower()
        self.session_authz_detail_level = "minimal" if authz_level == "minimal" else "full"
        self.gm_auth_token = str(gm_auth_token).strip() if gm_auth_token else None
        self.server.entitlement_guard = EntitlementGuard(entitlement_policy or {})
        self.input_safeguards = InputSafeguards(
            max_command_chars=max_command_chars,
            max_envelope_bytes=max_envelope_bytes,
            command_rate_limit_per_sec=command_rate_limit_per_sec,
            command_burst=command_burst,
        )
        self._gm_auth_failures: Dict[str, int] = {}
        self._gm_auth_cooldown_until: Dict[str, float] = {}
        # Back-compat for current tests.
        self._assets = self.assets._assets
        self._asset_locks = self.assets._asset_locks

    def effective_settings(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "save_file": self.server.current_save_file,
            "asset_db": self.assets._asset_db.execute("PRAGMA database_list").fetchone()[2] if self.assets else ":memory:",
            "content_set": self._content_set_summary(),
            "feature_profile": getattr(self.server.feature_profile, "raw", {}),
            "feature_profile_modes": {
                "world": self.server.feature_profile.resolved_world_mode(),
                "combat": self.server.feature_profile.combat_mode,
                "weather": self.server.feature_profile.weather_mode,
                "world_effects": self.server.feature_profile.world_effects_mode,
                "authoring": self.server.feature_profile.authoring_mode,
                "world_mutation": self.server.feature_profile.world_mutation_mode,
                "mods": self.server.feature_profile.mods_mode,
            },
            "require_character_creation": bool(self.server.require_character_creation),
        }

    def _content_set_summary(self) -> dict[str, Any] | None:
        content_set = getattr(self.server, "content_set", None)
        if content_set is None:
            return None
        return {
            "id": content_set.content_set_id,
            "title": content_set.title,
            "version": content_set.version,
            "manifest_path": str(content_set.manifest_path),
            "start": {
                "region_id": content_set.start_region_id,
                "room_id": content_set.start_room_id,
            },
            "game_contract": content_set.game_contract.to_payload(),
        }

    def build_server_policy_payload(self, session_id: str | None = None) -> dict[str, Any]:
        profile = self.server.feature_profile
        world_mode = profile.resolved_world_mode()
        raw_profile = getattr(profile, "raw", {})
        raw_party = raw_profile.get("party", {}) if isinstance(raw_profile, dict) else {}
        if not isinstance(raw_party, dict):
            raw_party = {}
        shared_quest_policy = str(raw_party.get("shared_quest_policy", "leader_driven")).strip().lower() or "leader_driven"
        shared_rewards_policy = str(raw_party.get("shared_rewards_policy", "split")).strip().lower() or "split"
        loot_policy = str(raw_party.get("loot_policy", "round_robin")).strip().lower() or "round_robin"
        invite_conflict_policy = str(raw_party.get("invite_conflict_policy", "replace_existing")).strip().lower() or "replace_existing"
        offline_invites_supported = raw_party.get("offline_invites_supported", True)
        if isinstance(offline_invites_supported, str):
            offline_invites_supported = offline_invites_supported.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        else:
            offline_invites_supported = bool(offline_invites_supported)
        shard_session_resume_policy = str(self.server.shard_policy_value("session_resume_policy", "enabled")).strip().lower() or "enabled"
        shard_disconnect_timeout_policy = str(self.server.shard_policy_value("disconnect_timeout_policy", "indefinite")).strip().lower() or "indefinite"
        shard_disconnect_timeout_seconds = self.server.shard_disconnect_grace_window_seconds()
        shard_persistence_scope = str(self.server.shard_policy_value("persistence_scope", "world_and_players")).strip().lower() or "world_and_players"
        shard_late_join_policy = str(self.server.shard_policy_value("late_join_policy", "enabled")).strip().lower() or "enabled"
        shard_world_clock_policy = str(self.server.shard_policy_value("world_clock_policy", "always_on")).strip().lower() or "always_on"
        shard_background_simulation_policy = str(self.server.shard_policy_value("background_simulation_policy", "always_on")).strip().lower() or "always_on"
        shard_runtime = self.server.build_shard_runtime_payload()
        shard_admission_reason = self.server.shard_new_session_admission_block_reason()
        shard_operator_locks_required = self.server.shard_policy_value(
            "operator_locks_required",
            str(profile.authoring_mode).strip().lower() != "disabled",
        )
        if isinstance(shard_operator_locks_required, str):
            shard_operator_locks_required = shard_operator_locks_required.strip().lower() not in {"0", "false", "no", "off", "disabled"}
        else:
            shard_operator_locks_required = bool(shard_operator_locks_required)
        payload: dict[str, Any] = {
            "content_set": self._content_set_summary(),
            "profile_modes": {
                "world": world_mode,
                "combat": profile.combat_mode,
                "weather": profile.weather_mode,
                "world_effects": profile.world_effects_mode,
                "authoring": profile.authoring_mode,
                "world_mutation": profile.world_mutation_mode,
                "mods": profile.mods_mode,
            },
            "feature_flags": {
                "authoring_allowed": profile.authoring_allowed(),
                "world_mutation_allowed": profile.world_mutation_allowed(),
                "weather_enabled": profile.weather_enabled(),
                "world_effects_enabled": profile.world_effects_enabled(),
                "combat_enabled": profile.combat_mode == "enabled",
                "party_supported": world_mode == "co_op_party",
                "persistent_world": world_mode == "persistent_shard",
            },
            "party_policy": {
                "enabled": world_mode == "co_op_party",
                "invite_required": True,
                "leader_controls_membership": True,
                "decline_supported": True,
                "cancel_supported": True,
                "invite_conflict_policy": invite_conflict_policy,
                "offline_invites_supported": bool(offline_invites_supported),
                "shared_quest_policy": shared_quest_policy,
                "shared_rewards_policy": shared_rewards_policy,
                "loot_policy": loot_policy,
            },
            "shard_policy": {
                "enabled": world_mode == "persistent_shard",
                "session_resume_policy": shard_session_resume_policy,
                "disconnect_timeout_policy": shard_disconnect_timeout_policy,
                "disconnect_timeout_seconds": float(shard_disconnect_timeout_seconds),
                "persistence_scope": shard_persistence_scope,
                "late_join_policy": shard_late_join_policy,
                "world_clock_policy": shard_world_clock_policy,
                "background_simulation_policy": shard_background_simulation_policy,
                "operator_locks_required": bool(shard_operator_locks_required),
                "runtime_state": str(shard_runtime.get("state", "normal")),
                "runtime_message": str(shard_runtime.get("message", "")),
                "tick_enabled": bool(shard_runtime.get("tick_enabled", True)),
                "gameplay_enabled": bool(shard_runtime.get("gameplay_enabled", True)),
                "character_creation_enabled": bool(shard_runtime.get("character_creation_enabled", True)),
                "new_session_admission_enabled": shard_admission_reason == "",
                "new_session_admission_reason": shard_admission_reason,
                "diagnostics": self.server.build_shard_diagnostics_payload(),
            },
            "active_providers": {
                "weather": str(getattr(self.server.weather_provider, "provider_id", getattr(self.server.weather_provider, "mode", "unknown"))),
                "world_effects": str(getattr(self.server.world_effects_provider, "provider_id", getattr(self.server.world_effects_provider, "mode", "unknown"))),
            },
            "auth_policy": {
                "gm_auth_configured": bool(self.gm_auth_token),
                "gm_capability_name": "authoring.gm",
                "authoring_requires_gm": str(profile.authoring_mode).strip().lower() == "gm_only",
                "gm_auth_failures_for_cooldown": 3,
                "gm_auth_cooldown_seconds": 30,
            },
            "entitlement_policy": {
                "default_session_grants": list(self.server.entitlement_guard.default_grants),
                "gates": self.server.entitlement_guard.describe_gates(),
            },
            "abuse_policy": {
                "max_command_chars": int(self.input_safeguards.max_command_chars),
                "max_envelope_bytes": int(self.input_safeguards.max_envelope_bytes),
                "command_rate_limit_per_sec": float(self.input_safeguards.command_rate_limit_per_sec),
                "command_burst": int(self.input_safeguards.command_burst),
            },
        }
        if world_mode == "finite_adventure" and self.server.world.has_capability("quests"):
            payload["adventure_policy"] = {
                "enabled": True,
                "default_campaign_id": self.server.finite_adventure_default_campaign_id(),
                "replay_supported": self.server.finite_adventure_replay_supported(),
                "checkpoint_policy": self.server.finite_adventure_checkpoint_policy(),
                "run_state": self.server.build_finite_adventure_state_payload(session_id or ""),
            }
        payload["require_character_creation"] = bool(self.server.require_character_creation)
        if session_id is not None and self.session_authz_detail_level == "full":
            payload["session_entitlements"] = self._session_entitlements(session_id)
        return payload

    def build_operator_policy_payload(self, session_id: str | None = None) -> dict[str, Any]:
        return {
            "profile_source_path": str(getattr(self.server, "feature_profile_source_path", "") or ""),
            "boot_warnings": list(getattr(self.server, "boot_warnings", [])),
            "boot_warnings_structured": list(getattr(self.server, "boot_warning_records", [])),
            "startup_diagnostics": self.build_startup_diagnostics_payload(),
            "server_policy": self.build_server_policy_payload(session_id),
            "operator_catalog": self.build_operator_catalog_payload(session_id),
        }

    def build_startup_diagnostics_payload(self) -> dict[str, Any]:
        warning_records = list(getattr(self.server, "boot_warning_records", []))
        warning_codes: dict[str, int] = {}
        for record in warning_records:
            code = str(record.get("code", "server.unknown")).strip() or "server.unknown"
            warning_codes[code] = warning_codes.get(code, 0) + 1

        return {
            "content_set": self._content_set_summary(),
            "warning_count": len(warning_records),
            "warning_codes": dict(sorted(warning_codes.items())),
            "boot_warning_fail_codes": sorted(list(getattr(self.server, "boot_warning_fail_codes", set()))),
        }

    def _operator_action_entitlement_gate(self, domain: str, action: str) -> str:
        key = f"{domain}:{action}"
        map_ = {
            "Profiles:Apply Selected": "operator.profile.apply",
            "World Effects:Use Provider": "operator.world_effects.manage",
            "Shard:Set Normal": "operator.shard.manage",
            "Shard:Set Drain": "operator.shard.manage",
            "Shard:Set Freeze": "operator.shard.manage",
            "Shard:Set Maintenance": "operator.shard.manage",
            "Authoring:Acquire Lock": "creator_sdk.authoring",
            "Authoring:Renew Lock": "creator_sdk.authoring",
            "Authoring:Release Lock": "creator_sdk.authoring",
            "Authoring:Edit Next": "creator_sdk.authoring",
            "Authoring:Edit Stale": "creator_sdk.authoring",
            "Audit:Shard Runtime": "operator.shard.manage",
            "Audit:Stale Refs": "operator.audit.stale_refs",
            "Audit:Boot Warnings": "operator.audit.boot_warnings",
        }
        return map_.get(key, "")

    def _operator_action_command_text(self, domain: str, action: str) -> str:
        map_ = {
            "Policy:Fetch Policy": "server policy",
            "Profiles:List Profiles": "profile list",
            "Profiles:Apply Selected": "profile apply",
            "Shard:Status": "shard status",
            "Shard:Set Normal": "shard mode normal",
            "Shard:Set Drain": "shard mode drain",
            "Shard:Set Freeze": "shard mode freeze",
            "Shard:Set Maintenance": "shard mode maintenance",
            "World Effects:Providers": "effects providers",
            "World Effects:Status": "effects status",
            "World Effects:Use Provider": "effects use",
            "Auth:GM Status": "gm status",
            "Auth:GM Deauth": "gm deauth",
            "Auth:GM Auth": "gm auth",
            "Audit:Shard Runtime": "audit shard",
            "Audit:Stale Refs": "audit stale-refs",
            "Audit:Boot Warnings": "audit boot-warnings",
        }
        return map_.get(f"{domain}:{action}", "")

    def _command_metadata_for_text(self, command_text: str) -> dict[str, Any]:
        text = str(command_text).strip().lower()
        if not text:
            return {}
        parts = text.split()
        registry = get_registered_commands()
        for i in range(len(parts), 0, -1):
            candidate = " ".join(parts[:i])
            if candidate in registry:
                return dict(registry.get(candidate, {}))
        return {}

    def _operator_action_requirements(self, domain: str, action: str) -> dict[str, Any]:
        requirements: dict[str, Any] = {}
        command_text = self._operator_action_command_text(domain, action)
        cmd_meta = self._command_metadata_for_text(command_text)
        caps = cmd_meta.get("capabilities", [])
        if isinstance(caps, list) and "authoring.gm" in [str(c).strip() for c in caps]:
            requirements["requires_gm"] = True
        ents = cmd_meta.get("entitlements", [])
        if isinstance(ents, list):
            ent_names = [str(e).strip() for e in ents if str(e).strip()]
            if ent_names:
                requirements["requires_entitlement"] = ent_names[0]
        gate = self._operator_action_entitlement_gate(domain, action)
        if gate and "requires_entitlement" not in requirements:
            requirements["requires_entitlement"] = gate
        if domain == "World Effects" and action == "Use Provider":
            requirements["requires_gm"] = True
        return requirements

    def _session_entitlements(self, session_id: str | None) -> list[str]:
        if not session_id:
            return []
        session = self.server.sessions.get(session_id)
        if session is None:
            return []
        return list(getattr(session, "entitlements", []))

    def _check_session_entitlement(self, session_id: str | None, gate_name: str) -> tuple[bool, str]:
        if gate_name.strip() == "":
            return True, ""
        return self.server.entitlement_guard.check(gate_name, self._session_entitlements(session_id))

    def _entitlement_error_event(self, session_id: str, gate_name: str, reason: str = "") -> dict[str, Any]:
        text = reason.strip() if reason.strip() else f"Feature requires entitlement gate '{gate_name}'."
        return self.server._event("error", session_id, text)

    def build_operator_catalog_payload(self, session_id: str | None = None) -> dict[str, Any]:
        profile = self.server.feature_profile
        domains: dict[str, list[str]] = {
            "Policy": ["Fetch Policy"],
            "Profiles": ["List Profiles", "Apply Selected"],
            "Auth": ["GM Status", "GM Deauth"],
        }
        if profile.resolved_world_mode() == "persistent_shard":
            domains["Shard"] = ["Status", "Set Normal", "Set Drain", "Set Freeze", "Set Maintenance"]
        if bool(self.gm_auth_token):
            domains["Auth"].append("GM Auth")
        if profile.world_effects_enabled():
            domains["World Effects"] = ["Providers", "Status", "Use Provider"]
        if profile.authoring_allowed():
            domains["Authoring"] = ["Lock Status", "Acquire Lock", "Renew Lock", "Release Lock", "Edit Next", "Edit Stale"]
        domains["Audit"] = ["Stale Refs", "Boot Warnings"]
        if profile.resolved_world_mode() == "persistent_shard":
            domains["Audit"].insert(0, "Shard Runtime")
        filtered_domains: dict[str, list[str]] = {}
        requirements: dict[str, dict[str, Any]] = {}
        for domain, actions in domains.items():
            allowed_actions: list[str] = []
            for action in actions:
                req = self._operator_action_requirements(domain, action)
                gate = str(req.get("requires_entitlement", "")).strip()
                if req:
                    requirements[f"{domain}:{action}"] = req
                if session_id is not None and gate:
                    ok, _reason = self._check_session_entitlement(session_id, gate)
                    if not ok:
                        continue
                allowed_actions.append(action)
            if allowed_actions:
                filtered_domains[domain] = allowed_actions
        return {
            "domains": filtered_domains,
            "value_options": {
                "Profiles:Apply Selected": self._list_profile_presets(),
                "World Effects:Use Provider": self._list_world_effects_provider_ids(),
            },
            "requirements": requirements,
        }

    def build_profile_presets_payload(self) -> dict[str, Any]:
        return {
            "presets": self._list_profile_presets(),
            "active_profile_path": str(getattr(self.server, "feature_profile_source_path", "") or ""),
        }

    def _is_server_policy_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"server policy", "@server policy", "policy"}

    def _is_profile_list_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"profile list", "profiles"}

    def _is_shard_status_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"shard status", "shard"}

    def _parse_shard_mode_command(self, command_text: str) -> tuple[str, str]:
        normalized = str(command_text).strip()
        parts = normalized.split()
        if len(parts) < 3 or parts[0].lower() != "shard" or parts[1].lower() != "mode":
            return "", ""
        state = parts[2].strip().lower()
        message = normalized.split(None, 3)[3].strip() if len(parts) >= 4 else ""
        return state, message

    def _parse_gm_auth_command(self, command_text: str) -> str:
        parts = str(command_text).strip().split()
        if len(parts) >= 3 and parts[0].lower() == "gm" and parts[1].lower() == "auth":
            return " ".join(parts[2:]).strip()
        return ""

    def _parse_gm_command(self, command_text: str) -> tuple[str, str]:
        parts = str(command_text).strip().split()
        if len(parts) < 2 or parts[0].lower() != "gm":
            return "", ""
        subcommand = parts[1].strip().lower()
        remainder = " ".join(parts[2:]).strip() if len(parts) >= 3 else ""
        return subcommand, remainder

    def _is_gm_session(self, session_id: str) -> bool:
        session = self.server.sessions.get(session_id)
        if not session:
            return False
        return "authoring.gm" in getattr(session, "capabilities", [])

    def _build_auth_state_payload(self, session_id: str) -> dict[str, Any]:
        now = time.time()
        cooldown_until = float(self._gm_auth_cooldown_until.get(session_id, 0.0))
        cooldown_remaining = max(0.0, cooldown_until - now)
        profile = self.server.feature_profile
        payload = {
            "gm_granted": self._is_gm_session(session_id),
            "gm_auth_configured": bool(self.gm_auth_token),
            "gm_auth_cooldown_seconds": int(round(cooldown_remaining)),
            "authoring_mode": str(profile.authoring_mode),
            "authoring_requires_gm": str(profile.authoring_mode).strip().lower() == "gm_only",
        }
        if self.session_authz_detail_level == "full":
            payload["session_entitlements"] = self._session_entitlements(session_id)
        return payload

    def _handle_gm_auth_command(self, session_id: str, command_text: str) -> tuple[bool, dict[str, Any] | None]:
        token = self._parse_gm_auth_command(command_text)
        if token == "":
            return False, None
        now = time.time()
        cooldown_until = float(self._gm_auth_cooldown_until.get(session_id, 0.0))
        if cooldown_until > now:
            wait_s = int(max(1.0, round(cooldown_until - now)))
            return True, self.server._event(
                "error",
                session_id,
                "GM auth temporarily locked. Try again in %ds." % wait_s,
            )
        if not self.gm_auth_token:
            return True, self.server._event(
                "error",
                session_id,
                "GM auth is not configured on this server.",
            )
        if not hmac.compare_digest(token, self.gm_auth_token):
            failures = int(self._gm_auth_failures.get(session_id, 0)) + 1
            self._gm_auth_failures[session_id] = failures
            if failures >= 3:
                self._gm_auth_cooldown_until[session_id] = now + 30.0
                self._gm_auth_failures[session_id] = 0
                return True, self.server._event(
                    "error",
                    session_id,
                    "GM auth temporarily locked. Try again in 30s.",
                )
            return True, self.server._event(
                "error",
                session_id,
                "GM auth failed.",
            )
        self._gm_auth_failures[session_id] = 0
        self._gm_auth_cooldown_until.pop(session_id, None)
        session = self.server.sessions.get(session_id)
        if not session:
            return True, self.server._event("error", session_id, "Unknown session.")
        if "authoring.gm" not in session.capabilities:
            session.capabilities.append("authoring.gm")
        return True, self.server._event(
            "text",
            session_id,
            "GM auth granted for this session.",
        )

    def _handle_gm_deauth_command(self, session_id: str) -> tuple[bool, dict[str, Any] | None]:
        session = self.server.sessions.get(session_id)
        if not session:
            return True, self.server._event("error", session_id, "Unknown session.")
        session_caps = list(getattr(session, "capabilities", []))
        if "authoring.gm" in session_caps:
            session_caps = [cap for cap in session_caps if cap != "authoring.gm"]
            session.capabilities = session_caps
            return True, self.server._event("text", session_id, "GM auth revoked for this session.")
        return True, self.server._event("text", session_id, "GM auth is not active for this session.")

    def _handle_gm_status_command(self, session_id: str) -> tuple[bool, dict[str, Any] | None]:
        payload = self._build_auth_state_payload(session_id)
        summary = "GM session: %s | auth configured: %s | cooldown: %ds | authoring mode: %s" % (
            "yes" if bool(payload.get("gm_granted", False)) else "no",
            "yes" if bool(payload.get("gm_auth_configured", False)) else "no",
            int(payload.get("gm_auth_cooldown_seconds", 0)),
            str(payload.get("authoring_mode", "unknown")),
        )
        return True, self.server._event("text", session_id, summary)

    def _handle_gm_command(self, session_id: str, command_text: str) -> tuple[bool, list[dict[str, Any]]]:
        subcommand, remainder = self._parse_gm_command(command_text)
        if subcommand == "":
            return False, []

        if subcommand == "help":
            return True, [
                self.server._event("text", session_id, "GM commands: gm auth <token> | gm status | gm deauth"),
                self.server._event("auth_state", session_id, self._build_auth_state_payload(session_id)),
            ]
        if subcommand == "status":
            handled, event = self._handle_gm_status_command(session_id)
            events = [event] if event is not None else []
            if handled:
                events.append(self.server._event("auth_state", session_id, self._build_auth_state_payload(session_id)))
            return handled, events
        if subcommand == "deauth":
            handled, event = self._handle_gm_deauth_command(session_id)
            events = [event] if event is not None else []
            if handled:
                events.append(self.server._event("auth_state", session_id, self._build_auth_state_payload(session_id)))
            return handled, events
        if subcommand == "auth":
            gm_handled, gm_event = self._handle_gm_auth_command(session_id, "gm auth %s" % remainder)
            events: list[dict[str, Any]] = []
            if gm_event is not None:
                events.append(gm_event)
            if gm_handled:
                events.append(self.server._event("auth_state", session_id, self._build_auth_state_payload(session_id)))
            return gm_handled, events
        return True, [self.server._event("error", session_id, "Unknown gm subcommand. Use: gm help")]

    def _parse_profile_apply_command(self, command_text: str) -> str:
        parts = str(command_text).strip().split()
        if len(parts) >= 3 and parts[0].lower() == "profile" and parts[1].lower() == "apply":
            return parts[2].strip().lower()
        return ""

    def _is_world_effects_list_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"effects providers", "world effects providers", "effects list"}

    def _is_world_effects_status_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"effects status", "world effects status", "effects"}

    def _parse_world_effects_use_command(self, command_text: str) -> str:
        parts = str(command_text).strip().split()
        if len(parts) >= 3 and parts[0].lower() == "effects" and parts[1].lower() in {"use", "provider"}:
            return parts[2].strip().lower()
        if len(parts) >= 4 and parts[0].lower() == "world" and parts[1].lower() == "effects" and parts[2].lower() in {"use", "provider"}:
            return parts[3].strip().lower()
        return ""

    def _is_audit_stale_refs_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"audit stale-refs", "audit stale_refs", "audit stale refs"}

    def _is_audit_boot_warnings_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"audit boot-warnings", "audit boot_warnings", "audit boot warnings", "boot warnings"}

    def _is_audit_shard_command(self, command_text: str) -> bool:
        normalized = str(command_text).strip().lower()
        return normalized in {"audit shard", "audit shard-runtime", "audit shard_runtime", "audit shard runtime"}

    def _run_boot_warning_audit(self) -> dict[str, Any]:
        records = list(getattr(self.server, "boot_warning_records", []))
        by_code: dict[str, int] = {}
        for entry in records:
            code = str(entry.get("code", "server.unknown")).strip() or "server.unknown"
            by_code[code] = by_code.get(code, 0) + 1
        return {
            "audit": "boot_warnings",
            "warning_count": len(records),
            "codes": dict(sorted(by_code.items())),
            "warnings": records,
            "clean": len(records) == 0,
        }

    def _shard_status_payload(self) -> dict[str, Any]:
        runtime = self.server.build_shard_runtime_payload()
        runtime["world_mode"] = self.server.feature_profile.resolved_world_mode()
        runtime["diagnostics"] = self.server.build_shard_diagnostics_payload()
        return runtime

    def _run_shard_runtime_audit(self) -> dict[str, Any]:
        diagnostics = self.server.build_shard_diagnostics_payload()
        return {
            "audit": "shard_runtime",
            "clean": int(diagnostics.get("expired_grace_window_session_count", 0)) == 0,
            "diagnostics": diagnostics,
        }

    def _set_shard_mode(self, session_id: str, state: str, message: str = "") -> tuple[bool, str]:
        if self.server.feature_profile.resolved_world_mode() != "persistent_shard":
            return False, "Shard controls are available only in world mode 'persistent_shard'."
        return self.server.set_shard_runtime_state(state, message, changed_by_session_id=session_id)

    def _build_shard_mode_announcement(self, actor_session_id: str) -> str:
        runtime = self.server.build_shard_runtime_payload()
        actor = self.server.get_player_for_session(actor_session_id)
        actor_name = str(getattr(actor, "name", "")).strip() or "Operator"
        message = str(runtime.get("message", "")).strip()
        summary = f"{actor_name} set shard mode to {runtime.get('state', 'normal')}."
        if message:
            summary = f"{summary} {message}"
        return summary

    def _run_stale_ref_audit(self) -> dict[str, Any]:
        """Run the stale-reference audit against the server's data root.

        Imports ``audit_stale_references`` from the toolkit at runtime so the
        server module does not hard-depend on the toolkit's location at import
        time.  Falls back gracefully if the toolkit is not on the Python path.
        """
        import sys
        from pathlib import Path

        root_path = Path(self.server.world.content_root)
        if not root_path.is_dir():
            return {
                "audit": "stale_refs",
                "root": str(root_path),
                "issues": [],
                "error_count": 0,
                "warn_count": 0,
                "clean": True,
                "error": f"Data root does not exist: {root_path}",
            }

        # Add the project-level toolkit directory to sys.path if needed.
        toolkit_path = str(Path(__file__).parent.parent / "toolkit")
        if toolkit_path not in sys.path:
            sys.path.insert(0, toolkit_path)

        try:
            from stale_reference_audit import audit_stale_references  # type: ignore[import]
        except ImportError as exc:
            return {
                "audit": "stale_refs",
                "root": str(root_path),
                "issues": [],
                "error_count": 0,
                "warn_count": 0,
                "clean": True,
                "error": f"Audit toolkit not available: {exc}",
            }

        issues = audit_stale_references(root_path)
        error_count = sum(1 for line in issues if line.startswith("[ERROR]"))
        warn_count = sum(1 for line in issues if line.startswith("[WARN]"))
        return {
            "audit": "stale_refs",
            "root": str(root_path),
            "issues": issues,
            "error_count": error_count,
            "warn_count": warn_count,
            "clean": error_count == 0,
        }

    def _list_world_effects_provider_ids(self) -> list[str]:
        providers: list[str] = [
            "builtin.world_effects.default",
            "disabled.world_effects",
        ]
        providers.extend(sorted(self.server.custom_world_effects_providers.keys()))
        return providers

    def _world_effects_status_payload(self) -> dict[str, Any]:
        active_provider = str(
            getattr(
                self.server.world_effects_provider,
                "provider_id",
                getattr(self.server.world_effects_provider, "mode", "unknown"),
            )
        )
        mode = str(self.server.feature_profile.world_effects_mode)
        return {
            "mode": mode,
            "active_provider": active_provider,
            "available_providers": self._list_world_effects_provider_ids(),
        }

    def _set_world_effects_provider(self, session_id: str, provider_id: str) -> tuple[bool, str]:
        if not self._is_gm_session(session_id):
            return False, "World-effects provider changes require a GM session. Run: gm auth <token>"
        requested = str(provider_id).strip().lower()
        if requested == "":
            return False, "Usage: effects use <provider_id>"
        available = self._list_world_effects_provider_ids()
        if requested not in available:
            return False, "Unknown world-effects provider '%s'. Use: effects providers" % requested

        if requested == "builtin.world_effects.default":
            self.server.feature_profile.world_effects_mode = "enabled"
            if isinstance(self.server.feature_profile.raw, dict):
                node = dict(self.server.feature_profile.raw.get("world_effects", {}))
                node["mode"] = "enabled"
                node.pop("provider_id", None)
                self.server.feature_profile.raw["world_effects"] = node
            self.server._sync_providers_with_profile()
            return True, "World-effects provider set to builtin."

        if requested == "disabled.world_effects":
            self.server.feature_profile.world_effects_mode = "disabled"
            if isinstance(self.server.feature_profile.raw, dict):
                node = dict(self.server.feature_profile.raw.get("world_effects", {}))
                node["mode"] = "disabled"
                node.pop("provider_id", None)
                self.server.feature_profile.raw["world_effects"] = node
            self.server._sync_providers_with_profile()
            return True, "World-effects provider disabled."

        self.server.feature_profile.world_effects_mode = "custom"
        if isinstance(self.server.feature_profile.raw, dict):
            self.server.feature_profile.raw["world_effects"] = {
                "mode": "custom",
                "provider_id": requested,
            }
        self.server._sync_providers_with_profile()
        return True, "World-effects provider set to '%s'." % requested

    def _profile_presets_dir(self) -> str:
        return os.path.join(self.server.world.content_root, "profiles")

    def _list_profile_presets(self) -> list[str]:
        presets_dir = self._profile_presets_dir()
        if not os.path.isdir(presets_dir):
            return []
        names: list[str] = []
        for entry in os.listdir(presets_dir):
            if not entry.endswith(".profile.json"):
                continue
            names.append(entry.removesuffix(".profile.json"))
        names.sort()
        return names

    def _apply_profile_preset(self, preset_name: str) -> tuple[bool, str]:
        requested = str(preset_name).strip().lower()
        if requested == "":
            return False, "Usage: profile apply <preset_name>"
        preset_path = os.path.join(self._profile_presets_dir(), "%s.profile.json" % requested)
        if not os.path.exists(preset_path):
            return False, "Unknown profile preset '%s'." % requested

        self.server.feature_profile_source_path = str(preset_path)
        self.server.reset_boot_warnings_for_profile(FeatureProfile.load(preset_path))
        self.server._sync_providers_with_profile()
        return True, "Profile applied: %s" % requested

    async def start(self) -> None:
        self._tcp_server = await asyncio.start_server(self._handle_client, self.host, self.port)
        addrs = ", ".join(str(sock.getsockname()) for sock in self._tcp_server.sockets or [])
        print(f"PoC server listening on {addrs}")
        async with self._tcp_server:
            await self._tcp_server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        import uuid
        unique_player_id = f"player_{uuid.uuid4().hex[:8]}"
        session = self.server.create_session(
            player_id=unique_player_id,
            entitlements=self.session_default_entitlements,
        )
        self.server.mark_session_connected(session.session_id)
        session.capabilities = list(self.session_default_capabilities)
        self._session_writers[session.session_id] = writer
        await self._send_event(
            writer,
            self.server._event(
                "hello",
                session.session_id,
                {
                    "message": "connected",
                    "session_id": session.session_id,
                    "session_capabilities": list(session.capabilities),
                    "has_character": self.server.get_player_for_session(session.session_id) is not None,
                    "auth_state": self._build_auth_state_payload(session.session_id),
                    "party_state": self.server.build_party_state_payload(session.session_id),
                    "startup_diagnostics": self.build_startup_diagnostics_payload(),
                    "server_policy": self.build_server_policy_payload(session.session_id),
                    "operator_catalog": self.build_operator_catalog_payload(session.session_id),
                },
            ),
        )
        await self._send_event(
            writer,
            self.server._event(
                "auth_state",
                session.session_id,
                self._build_auth_state_payload(session.session_id),
            ),
        )
        await self._send_event(
            writer,
            self.server._event(
                "lock_state",
                session.session_id,
                self._build_lock_state_payload(),
            ),
        )

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                ok_size, size_reason = self.input_safeguards.check_envelope_size(len(line))
                if not ok_size:
                    await self._send_event(
                        writer,
                        self.server._event("error", session.session_id, size_reason),
                    )
                    continue
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                envelope: Dict[str, Any]
                try:
                    envelope = json.loads(text)
                except json.JSONDecodeError:
                    # Convenience mode: plain text lines are treated as commands.
                    envelope = {
                        "type": "command",
                        "session_id": session.session_id,
                        "command_text": text,
                        "client_capabilities": {"plain_text_mode": True},
                    }

                if envelope.get("type") != "resume_session":
                    for event in self.server.prune_expired_shard_sessions():
                        await self._broadcast_event(event)

                if envelope.get("type") == "disconnect":
                    await self._send_event(writer, self.server._event("goodbye", session.session_id, "disconnected"))
                    break
                if envelope.get("type") == "resume_session":
                    requested_session_id = str(envelope.get("session_id", "")).strip()
                    allowed_resume, resume_reason = self.server.validate_resume_session_target(requested_session_id)
                    if allowed_resume:
                        ephemeral_session_id = session.session_id
                        resumed_session = self.server.sessions[requested_session_id]
                        self._session_writers.pop(ephemeral_session_id, None)
                        self.server.sessions.pop(ephemeral_session_id, None)
                        self.input_safeguards.clear_session(ephemeral_session_id)
                        self._gm_auth_failures.pop(ephemeral_session_id, None)
                        self._gm_auth_cooldown_until.pop(ephemeral_session_id, None)

                        session = resumed_session
                        self.server.mark_session_connected(session.session_id)
                        self._session_writers[session.session_id] = writer

                        await self._send_event(
                            writer,
                            self.server._event(
                                "session_resumed",
                                session.session_id,
                                {"session_id": session.session_id, "resumed": True},
                            ),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "auth_state",
                                session.session_id,
                                self._build_auth_state_payload(session.session_id),
                            ),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "server_policy",
                                session.session_id,
                                self.build_operator_policy_payload(session.session_id),
                            ),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "party_state",
                                session.session_id,
                                self.server.build_party_state_payload(session.session_id),
                            ),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "lock_state",
                                session.session_id,
                                self._build_lock_state_payload(),
                            ),
                        )
                        for event in self.server.build_party_presence_sync_events_for_session(session.session_id):
                            target_id = str(event.get("session_id", ""))
                            if target_id == session.session_id:
                                continue
                            target_writer = self._session_writers.get(target_id)
                            if target_writer is not None:
                                await self._send_event(target_writer, event)
                    else:
                        await self._send_event(
                            writer,
                            self.server._event(
                                "error",
                                session.session_id,
                                resume_reason or "Resume rejected",
                            ),
                        )
                        for event in self.server.prune_expired_shard_sessions():
                            await self._broadcast_event(event)
                    continue
                allowed_budget, retry_after_s = self.input_safeguards.consume_rate_budget(session.session_id)
                if not allowed_budget:
                    await self._send_event(
                        writer,
                        self.server._event(
                            "error",
                            session.session_id,
                            "Rate limit exceeded. Retry in %.2fs." % retry_after_s,
                        ),
                    )
                    continue
                if self._is_mutation_envelope(envelope) and not self.server.feature_profile.world_mutation_allowed():
                    await self._send_event(
                        writer,
                        self.server._event("error", session.session_id, "World mutation is disabled by server profile."),
                    )
                    continue
                if self._is_authoring_envelope(envelope):
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "creator_sdk.authoring")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "creator_sdk.authoring", ent_reason),
                        )
                        continue
                    authoring_denial = self._authoring_denial_reason(session.session_id)
                    if authoring_denial:
                        await self._send_event(
                            writer,
                            self.server._event("error", session.session_id, authoring_denial),
                        )
                        continue
                if envelope.get("type") == "lock_acquire":
                    for event in self._handle_lock_acquire_envelope(session.session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_event(event)
                        else:
                            await self._send_event(writer, event)
                    continue
                if envelope.get("type") == "lock_release":
                    for event in self._handle_lock_release_envelope(session.session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_event(event)
                        else:
                            await self._send_event(writer, event)
                    continue
                if envelope.get("type") == "lock_renew":
                    for event in self._handle_lock_renew_envelope(session.session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_event(event)
                        else:
                            await self._send_event(writer, event)
                    continue
                if envelope.get("type") == "asset_update":
                    result_events = self._handle_asset_update_envelope(session.session_id, envelope)
                    for event in result_events:
                        if event.get("type") == "asset":
                            await self._broadcast_event(event)
                        else:
                            await self._send_event(writer, event)
                    continue
                if envelope.get("type") == "lock_status":
                    await self._send_event(
                        writer,
                        self.server._event(
                            "lock_state",
                            session.session_id,
                            self._build_lock_state_payload(),
                        ),
                    )
                    continue

                raw_command_text = str(envelope.get("command_text", "")).strip()
                command_text = raw_command_text.lower()
                gm_handled, gm_events = self._handle_gm_command(session.session_id, raw_command_text)
                if gm_handled:
                    for gm_event in gm_events:
                        await self._send_event(writer, gm_event)
                    continue
                translated, authoring_error = self._translate_authoring_shell_command(session.session_id, command_text)
                if authoring_error:
                    await self._send_event(writer, self.server._event("error", session.session_id, authoring_error))
                    continue
                if translated is not None:
                    if self._is_mutation_envelope(translated) and not self.server.feature_profile.world_mutation_allowed():
                        await self._send_event(
                            writer,
                            self.server._event("error", session.session_id, "World mutation is disabled by server profile."),
                        )
                        continue
                    if self._is_authoring_envelope(translated):
                        ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "creator_sdk.authoring")
                        if not ent_ok:
                            await self._send_event(
                                writer,
                                self._entitlement_error_event(session.session_id, "creator_sdk.authoring", ent_reason),
                            )
                            continue
                        authoring_denial = self._authoring_denial_reason(session.session_id)
                        if authoring_denial:
                            await self._send_event(
                                writer,
                                self.server._event("error", session.session_id, authoring_denial),
                            )
                            continue
                    if translated.get("type") == "lock_acquire":
                        for event in self._handle_lock_acquire_envelope(session.session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_event(event)
                            else:
                                await self._send_event(writer, event)
                        continue
                    if translated.get("type") == "lock_release":
                        for event in self._handle_lock_release_envelope(session.session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_event(event)
                            else:
                                await self._send_event(writer, event)
                        continue
                    if translated.get("type") == "lock_renew":
                        for event in self._handle_lock_renew_envelope(session.session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_event(event)
                            else:
                                await self._send_event(writer, event)
                        continue
                    if translated.get("type") == "asset_update":
                        result_events = self._handle_asset_update_envelope(session.session_id, translated)
                        for event in result_events:
                            if event.get("type") == "asset":
                                await self._broadcast_event(event)
                            else:
                                await self._send_event(writer, event)
                        continue
                    if translated.get("type") == "lock_status":
                        await self._send_event(
                            writer,
                            self.server._event(
                                "lock_state",
                                session.session_id,
                                self._build_lock_state_payload(),
                            ),
                        )
                        continue

                if command_text == "blighttest":
                    client_capabilities = envelope.get("client_capabilities", {})
                    await self._send_event(
                        writer,
                        self.server._event(
                            "text",
                            session.session_id,
                            self._build_blight_payload(client_capabilities),
                        ),
                    )
                    continue
                if command_text == "svgtest":
                    await self._send_event(
                        writer,
                        self.server._event(
                            "asset",
                            session.session_id,
                            self._build_svg_test_payload(),
                        ),
                    )
                    continue
                if self._is_server_policy_command(command_text):
                    await self._send_event(
                        writer,
                        self.server._event(
                            "server_policy",
                            session.session_id,
                            self.build_operator_policy_payload(session.session_id),
                        ),
                    )
                    continue
                if self._is_profile_list_command(command_text):
                    presets = self._list_profile_presets()
                    await self._send_event(
                        writer,
                        self.server._event(
                            "profile_presets",
                            session.session_id,
                            self.build_profile_presets_payload(),
                        ),
                    )
                    if presets:
                        await self._send_event(
                            writer,
                            self.server._event(
                                "text",
                                session.session_id,
                                "Available profiles: %s" % ", ".join(presets),
                            ),
                        )
                    else:
                        await self._send_event(
                            writer,
                            self.server._event("text", session.session_id, "No profile presets found."),
                        )
                    continue
                if self._is_shard_status_command(command_text):
                    payload = self._shard_status_payload()
                    await self._send_event(
                        writer,
                        self.server._event("shard_status", session.session_id, payload),
                    )
                    summary = "Shard mode=%s | tick=%s | gameplay=%s | character_creation=%s" % (
                        payload.get("state", "normal"),
                        "on" if bool(payload.get("tick_enabled", True)) else "off",
                        "on" if bool(payload.get("gameplay_enabled", True)) else "off",
                        "on" if bool(payload.get("character_creation_enabled", True)) else "off",
                    )
                    if str(payload.get("message", "")).strip():
                        summary = "%s | note=%s" % (summary, str(payload.get("message", "")).strip())
                    diagnostics = payload.get("diagnostics", {})
                    if not bool(diagnostics.get("new_session_admission_enabled", True)):
                        summary = "%s | admission=blocked" % summary
                    await self._send_event(
                        writer,
                        self.server._event("text", session.session_id, summary),
                    )
                    continue
                shard_mode_target, shard_mode_message = self._parse_shard_mode_command(raw_command_text)
                if shard_mode_target != "":
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.shard.manage")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.shard.manage", ent_reason),
                        )
                        continue
                    ok, message = self._set_shard_mode(session.session_id, shard_mode_target, shard_mode_message)
                    await self._send_event(
                        writer,
                        self.server._event("text" if ok else "error", session.session_id, message),
                    )
                    if ok:
                        await self._broadcast_shard_runtime_update(session.session_id)
                    continue
                profile_apply_target = self._parse_profile_apply_command(command_text)
                if profile_apply_target != "":
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.profile.apply")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.profile.apply", ent_reason),
                        )
                        continue
                    ok, message = self._apply_profile_preset(profile_apply_target)
                    if not ok:
                        await self._send_event(
                            writer,
                            self.server._event("error", session.session_id, message),
                        )
                    else:
                        await self._send_event(
                            writer,
                            self.server._event("text", session.session_id, message),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "server_policy",
                                session.session_id,
                                self.build_operator_policy_payload(session.session_id),
                            ),
                        )
                    continue
                if self._is_world_effects_list_command(command_text):
                    payload = self._world_effects_status_payload()
                    await self._send_event(
                        writer,
                        self.server._event("world_effects_providers", session.session_id, payload),
                    )
                    await self._send_event(
                        writer,
                        self.server._event(
                            "text",
                            session.session_id,
                            "World-effects providers: %s" % ", ".join(payload["available_providers"]),
                        ),
                    )
                    continue
                if self._is_world_effects_status_command(command_text):
                    payload = self._world_effects_status_payload()
                    await self._send_event(
                        writer,
                        self.server._event("world_effects_status", session.session_id, payload),
                    )
                    await self._send_event(
                        writer,
                        self.server._event(
                            "text",
                            session.session_id,
                            "World-effects mode=%s provider=%s"
                            % (payload["mode"], payload["active_provider"]),
                        ),
                    )
                    continue
                effects_use_target = self._parse_world_effects_use_command(command_text)
                if effects_use_target != "":
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.world_effects.manage")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.world_effects.manage", ent_reason),
                        )
                        continue
                    ok, message = self._set_world_effects_provider(session.session_id, effects_use_target)
                    event_type = "text" if ok else "error"
                    await self._send_event(
                        writer,
                        self.server._event(event_type, session.session_id, message),
                    )
                    if ok:
                        await self._send_event(
                            writer,
                            self.server._event(
                                "world_effects_status",
                                session.session_id,
                                self._world_effects_status_payload(),
                            ),
                        )
                        await self._send_event(
                            writer,
                            self.server._event(
                                "server_policy",
                                session.session_id,
                                self.build_operator_policy_payload(session.session_id),
                            ),
                        )
                    continue

                if self._is_audit_stale_refs_command(command_text):
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.audit.stale_refs")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.audit.stale_refs", ent_reason),
                        )
                    else:
                        result = self._run_stale_ref_audit()
                        await self._send_event(
                            writer,
                            self.server._event("audit_result", session.session_id, result),
                        )
                        summary = (
                            result.get("error")
                            or (
                                f"Audit clean: {result['root']}"
                                if result.get("clean")
                                else f"Audit found {result['error_count']} error(s), {result['warn_count']} warning(s) in {result['root']}"
                            )
                        )
                        await self._send_event(
                            writer,
                            self.server._event("text", session.session_id, summary),
                        )
                    continue
                if self._is_audit_boot_warnings_command(command_text):
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.audit.boot_warnings")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.audit.boot_warnings", ent_reason),
                        )
                    else:
                        result = self._run_boot_warning_audit()
                        await self._send_event(
                            writer,
                            self.server._event("audit_result", session.session_id, result),
                        )
                        summary = (
                            "Boot warnings: clean (0)"
                            if result.get("clean")
                            else f"Boot warnings: {result.get('warning_count', 0)} record(s), {len(result.get('codes', {}))} code(s)"
                        )
                        await self._send_event(
                            writer,
                            self.server._event("text", session.session_id, summary),
                        )
                    continue
                if self._is_audit_shard_command(command_text):
                    ent_ok, ent_reason = self._check_session_entitlement(session.session_id, "operator.shard.manage")
                    if not ent_ok:
                        await self._send_event(
                            writer,
                            self._entitlement_error_event(session.session_id, "operator.shard.manage", ent_reason),
                        )
                    else:
                        result = self._run_shard_runtime_audit()
                        await self._send_event(
                            writer,
                            self.server._event("audit_result", session.session_id, result),
                        )
                        diagnostics = result.get("diagnostics", {})
                        summary = (
                            "Shard runtime: %s connected / %s disconnected / %s expired"
                            % (
                                int(diagnostics.get("connected_session_count", 0)),
                                int(diagnostics.get("disconnected_session_count", 0)),
                                int(diagnostics.get("expired_grace_window_session_count", 0)),
                            )
                        )
                        await self._send_event(
                            writer,
                            self.server._event("text", session.session_id, summary),
                        )
                    continue

                envelope["session_id"] = session.session_id
                cmd_ok, cmd_reason = self.input_safeguards.check_command_text(str(envelope.get("command_text", "")))
                if not cmd_ok:
                    await self._send_event(
                        writer,
                        self.server._event("error", session.session_id, cmd_reason),
                    )
                    continue
                events = self.server.execute_command_envelope(envelope)
                for event in events:
                    target_id = event.get("session_id")
                    if target_id == "*" or target_id == "broadcast":
                        await self._broadcast_event(event)
                    elif target_id and target_id in self._session_writers:
                        await self._send_event(self._session_writers[target_id], event)
                    else:
                        await self._send_event(writer, event)
        finally:
            self.server.mark_session_disconnected(session.session_id)
            await self._release_session_locks(session.session_id)
            for event in self.server.build_party_presence_sync_events_for_session(session.session_id):
                target_id = str(event.get("session_id", ""))
                if target_id == session.session_id:
                    continue
                target_writer = self._session_writers.get(target_id)
                if target_writer is not None:
                    await self._send_event(target_writer, event)
            self.input_safeguards.clear_session(session.session_id)
            active_ids = set(self._session_writers.keys())
            active_ids.discard(session.session_id)
            self.input_safeguards.evict_stale_sessions(active_ids)
            self._session_writers.pop(session.session_id, None)
            self._gm_auth_failures.pop(session.session_id, None)
            self._gm_auth_cooldown_until.pop(session.session_id, None)
            writer.close()
            await writer.wait_closed()

    async def _send_event(self, writer: asyncio.StreamWriter, event: Dict[str, Any]) -> None:
        writer.write((json.dumps(event) + "\n").encode("utf-8"))
        await writer.drain()

    async def _broadcast_policy_update(self) -> None:
        for target_session_id, target_writer in list(self._session_writers.items()):
            await self._send_event(
                target_writer,
                self.server._event(
                    "server_policy",
                    target_session_id,
                    self.build_operator_policy_payload(target_session_id),
                ),
            )

    async def _broadcast_shard_runtime_update(self, actor_session_id: str) -> None:
        announcement = self._build_shard_mode_announcement(actor_session_id)
        status_payload = self._shard_status_payload()
        for target_session_id, target_writer in list(self._session_writers.items()):
            await self._send_event(
                target_writer,
                self.server._event("shard_status", target_session_id, status_payload),
            )
            if target_session_id != actor_session_id:
                await self._send_event(
                    target_writer,
                    self.server._event("text", target_session_id, announcement),
                )
        await self._broadcast_policy_update()

    def _translate_authoring_shell_command(
        self, session_id: str, command_text: str
    ) -> tuple[Dict[str, Any] | None, str | None]:
        text = command_text.strip()
        if not text.startswith("@"):
            return None, None

        if not self.server.feature_profile.authoring_allowed():
            return None, "Live authoring is disabled by server profile."

        parts = text.split()
        if not parts:
            return None, "Empty authoring command."

        cmd = parts[0].lower()
        if cmd == "@dig":
            if len(parts) < 2:
                return None, "Usage: @dig <asset_id> [acquire|release|renew]"
            asset_id = parts[1].strip()
            if asset_id == "":
                return None, "Usage: @dig <asset_id> [acquire|release|renew]"
            action = "acquire"
            if len(parts) >= 3:
                action = parts[2].strip().lower()
            lock_type_map = {
                "acquire": "lock_acquire",
                "release": "lock_release",
                "renew": "lock_renew",
            }
            event_type = lock_type_map.get(action)
            if event_type is None:
                return None, "Unknown @dig action. Use acquire, release, or renew."
            return {
                "type": event_type,
                "session_id": session_id,
                "payload": {"asset_id": asset_id},
            }, None

        if cmd == "@edit":
            if len(parts) < 3:
                return None, "Usage: @edit <asset_id> <next|stale>"
            asset_id = parts[1].strip()
            mode = parts[2].strip().lower()
            if asset_id == "":
                return None, "Usage: @edit <asset_id> <next|stale>"
            if mode not in {"next", "stale"}:
                return None, "Unknown @edit mode. Use next or stale."

            known_revision = int(self._assets.get(asset_id, {}).get("revision", 1))
            base_revision = known_revision if mode == "next" else max(0, known_revision - 1)
            return {
                "type": "asset_update",
                "session_id": session_id,
                "payload": {
                    "asset_id": asset_id,
                    "base_revision": base_revision,
                    "svg": self._build_authoring_edit_svg(),
                    "alt_text": "Edited emblem from authoring shell.",
                },
            }, None

        return None, None

    def _build_authoring_edit_svg(self) -> str:
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>"
            "<rect width='32' height='32' fill='white'/>"
            "<rect x='1' y='1' width='30' height='30' fill='black'/>"
            "<rect x='6' y='6' width='20' height='20' fill='white'/>"
            "<rect x='12' y='12' width='8' height='8' fill='black'/>"
            "</svg>"
        )

    def _is_mutation_envelope(self, envelope: Dict[str, Any]) -> bool:
        envelope_type = str(envelope.get("type", "")).strip().lower()
        if envelope_type in {"lock_acquire", "lock_release", "lock_renew", "asset_update"}:
            return True
        # Guard: future protocol additions in these
        # namespaces are world-authoring mutations unless explicitly exempted.
        return envelope_type.startswith("lock_") or envelope_type.startswith("asset_")

    def _is_authoring_envelope(self, envelope: Dict[str, Any]) -> bool:
        envelope_type = str(envelope.get("type", "")).strip().lower()
        return envelope_type in {"lock_acquire", "lock_release", "lock_renew", "asset_update"}

    def _authoring_denial_reason(self, session_id: str) -> str | None:
        mode = str(self.server.feature_profile.authoring_mode).strip().lower()
        if mode == "disabled":
            return "Live authoring is disabled by server profile."
        if mode == "gm_only":
            session = self.server.sessions.get(session_id)
            session_caps = getattr(session, "capabilities", []) if session else []
            if "authoring.gm" not in session_caps:
                return "Live authoring is restricted to GM sessions by server profile."
        return None

    def _build_blight_payload(self, client_capabilities: Any) -> Dict[str, Any]:
        caps: Dict[str, Any] = client_capabilities if isinstance(client_capabilities, dict) else {}
        reduced_motion: bool = bool(caps.get("reduced_motion", False))
        screen_reader_mode: bool = bool(caps.get("screen_reader_mode", False))

        text = "The air tastes metallic and wrong."
        if screen_reader_mode:
            text = "[Atmosphere: blight high] The air tastes metallic and wrong."

        if reduced_motion:
            return {"text": text, "fx": {"blight": 0.0}}
        return {"text": text, "fx": {"blight": 0.85}}

    def _build_svg_test_payload(self) -> Dict[str, Any]:
        return self.assets.build_svg_test_payload()

    def _handle_asset_update_envelope(self, session_id: str, envelope: Dict[str, Any]) -> list[Dict[str, Any]]:
        return self.assets.handle_asset_update(session_id, envelope)

    def _handle_lock_acquire_envelope(self, session_id: str, envelope: Dict[str, Any]) -> list[Dict[str, Any]]:
        return self.assets.handle_lock_acquire(session_id, envelope)

    def _handle_lock_release_envelope(self, session_id: str, envelope: Dict[str, Any]) -> list[Dict[str, Any]]:
        return self.assets.handle_lock_release(session_id, envelope)

    def _handle_lock_renew_envelope(self, session_id: str, envelope: Dict[str, Any]) -> list[Dict[str, Any]]:
        return self.assets.handle_lock_renew(session_id, envelope)

    def _expire_stale_locks(self) -> None:
        self.assets._expire_stale_locks()

    def _build_lock_state_payload(self) -> Dict[str, Any]:
        return self.assets.build_lock_state_payload()

    def _sanitize_svg(self, svg: str) -> str:
        return self.assets.sanitize_svg(svg)

    async def _broadcast_event(self, event: Dict[str, Any]) -> None:
        dead_sessions: list[str] = []
        for session_id, writer in self._session_writers.items():
            try:
                await self._send_event(writer, event)
            except Exception:
                dead_sessions.append(session_id)
        for session_id in dead_sessions:
            self._session_writers.pop(session_id, None)

    async def _release_session_locks(self, session_id: str) -> None:
        for delta in self.assets.release_locks_for_session(session_id):
            await self._broadcast_event(
                self.server._event(
                    "lock_state_delta",
                    session_id,
                    delta,
                )
            )

    def shutdown(self) -> None:
        self.assets.close()
        self.server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC TCP JSON-line MUD server")
    parser.add_argument("--config", default="server/config/server_config.json", help="Master server config JSON path.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--save", "-s", default=None)
    parser.add_argument("--asset-db", default=None)
    parser.add_argument("--content-set", required=True, help="Content-set directory or manifest path.")
    args = parser.parse_args()
    config_payload = load_server_config(args.config)
    settings = resolve_server_settings(
        "tcp",
        config_payload,
        args.host,
        args.port,
        args.save,
        args.asset_db,
        args.config,
    )

    app = JsonLineMudServer(
        settings.host,
        settings.port,
        settings.save_file,
        asset_db_path=settings.asset_db,
        content_set_path=args.content_set,
        session_default_capabilities=settings.session_default_capabilities,
        session_default_entitlements=settings.session_default_entitlements,
        session_authz_detail_level=settings.session_authz_detail_level,
        gm_auth_token=settings.session_gm_auth_token,
        entitlement_policy=settings.entitlement_policy,
        max_command_chars=settings.abuse_max_command_chars,
        max_envelope_bytes=settings.abuse_max_envelope_bytes,
        command_rate_limit_per_sec=settings.abuse_command_rate_limit_per_sec,
        command_burst=settings.abuse_command_burst,
        starter_items=settings.world_bootstrap_starter_items,
        require_character_creation=settings.session_require_character_creation,
        boot_warning_fail_codes=settings.boot_warning_fail_codes,
    )
    for warning in app.server.boot_warnings:
        print("Feature profile warning:", warning)
    print(
        "Effective server settings:",
        json.dumps(
            {
                "transport": "tcp",
                "config_path": settings.config_path,
                "host": settings.host,
                "port": settings.port,
                "save_file": settings.save_file,
                "asset_db": settings.asset_db,
                "content_set": app.effective_settings()["content_set"],
                "feature_profile_modes": {
                    "combat": app.server.feature_profile.combat_mode,
                    "weather": app.server.feature_profile.weather_mode,
                    "world_effects": app.server.feature_profile.world_effects_mode,
                    "authoring": app.server.feature_profile.authoring_mode,
                    "world_mutation": app.server.feature_profile.world_mutation_mode,
                    "mods": app.server.feature_profile.mods_mode,
                },
                "require_character_creation": bool(app.server.require_character_creation),
            },
            separators=(",", ":"),
        ),
    )
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
