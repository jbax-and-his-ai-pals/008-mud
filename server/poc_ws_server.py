import argparse
import asyncio
import json
from typing import Any

from poc_server import JsonLineMudServer
from engine.server.transport.base import MSGPACK_AVAILABLE
from engine.server.transport.websocket_transport import WebSocketTransport
from engine.server.protocol import PROTOCOL_VERSION
from engine.server.feature_profile import FeatureProfile
from engine.server.server_config import load_server_config, resolve_server_settings


class JsonWebSocketMudServer:
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
        self.core = JsonLineMudServer(
            host,
            port,
            save_file,
            asset_db_path=asset_db_path,
            content_set_path=content_set_path,
            feature_profile=feature_profile,
            session_default_capabilities=session_default_capabilities,
            session_default_entitlements=session_default_entitlements,
            session_authz_detail_level=session_authz_detail_level,
            gm_auth_token=gm_auth_token,
            entitlement_policy=entitlement_policy,
            max_command_chars=max_command_chars,
            max_envelope_bytes=max_envelope_bytes,
            command_rate_limit_per_sec=command_rate_limit_per_sec,
            command_burst=command_burst,
            starter_items=starter_items,
            require_character_creation=require_character_creation,
            boot_warning_fail_codes=boot_warning_fail_codes,
        )
        # Values are WebSocketTransport instances (not raw sockets) so that
        # each session's codec preference is respected during broadcast.
        self._ws_sessions: dict[str, WebSocketTransport] = {}

    async def start(self) -> None:
        try:
            import websockets
            from websockets.exceptions import ConnectionClosed
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency 'websockets'. Install with: pip install websockets"
            ) from exc

        async def _handler(websocket: Any) -> None:
            try:
                await self._handle_websocket_client(websocket)
            except ConnectionClosed:
                pass

        async with websockets.serve(_handler, self.host, self.port):
            print(f"PoC WebSocket server listening on ws://{self.host}:{self.port}")
            await asyncio.Future()

    def shutdown(self) -> None:
        self.core.shutdown()

    async def _handle_websocket_client(self, websocket: Any) -> str:
        session = self.core.server.create_session(entitlements=self.core.session_default_entitlements)
        session.capabilities = list(self.core.session_default_capabilities)
        active_session_id = session.session_id
        self.core.server.mark_session_connected(active_session_id)
        transport = WebSocketTransport(websocket)

        # Hello and lock_state are sent before the client has spoken, so they
        # are always JSON regardless of the eventual codec.  server_capabilities
        # tells the client which transports are available.
        await transport.send_event(
            self.core.server._event(
                "hello",
                active_session_id,
                {
                    "message": "connected",
                    "session_id": active_session_id,
                    "session_capabilities": list(session.capabilities),
                    "has_character": self.core.server.get_player_for_session(active_session_id) is not None,
                    "auth_state": self.core._build_auth_state_payload(active_session_id),
                    "party_state": self.core.server.build_party_state_payload(active_session_id),
                    "server_protocol_version": PROTOCOL_VERSION,
                    "server_capabilities": {
                        "transports": ["json", "msgpack"] if MSGPACK_AVAILABLE else ["json"],
                    },
                    "startup_diagnostics": self.core.build_startup_diagnostics_payload(),
                    "server_policy": self.core.build_server_policy_payload(active_session_id),
                    "operator_catalog": self.core.build_operator_catalog_payload(active_session_id),
                },
            )
        )
        await transport.send_event(
            self.core.server._event(
                "auth_state",
                active_session_id,
                self.core._build_auth_state_payload(active_session_id),
            )
        )
        await transport.send_event(
            self.core.server._event(
                "lock_state",
                active_session_id,
                self.core._build_lock_state_payload(),
            )
        )

        # Store the transport so broadcast can use per-session codecs.
        self._ws_sessions[active_session_id] = transport

        first_message = True
        try:
            while True:
                raw = await websocket.recv()
                if raw is None:
                    break
                raw_len = len(raw) if isinstance(raw, (bytes, bytearray)) else len(str(raw).encode("utf-8", errors="ignore"))
                ok_size, size_reason = self.core.input_safeguards.check_envelope_size(raw_len)
                if not ok_size:
                    await transport.send_event(
                        self.core.server._event("error", active_session_id, size_reason)
                    )
                    continue

                # Codec is locked on the first non-empty message.
                if first_message:
                    transport.negotiate_codec(raw)
                    first_message = False

                # Normalise to a non-empty check without losing raw bytes.
                if isinstance(raw, (bytes, bytearray)):
                    if not raw.strip():
                        continue
                else:
                    if not str(raw).strip():
                        continue

                try:
                    envelope = transport.decode(raw)
                except Exception:
                    await transport.send_event(
                        self.core.server._event("error", active_session_id, "Invalid envelope")
                    )
                    continue

                if envelope.get("type") != "resume_session":
                    for event in self.core.server.prune_expired_shard_sessions():
                        await self._broadcast_ws_event(event)

                if envelope.get("type") == "disconnect":
                    await transport.send_event(
                        self.core.server._event("goodbye", active_session_id, "disconnected")
                    )
                    break
                allowed_budget, retry_after_s = self.core.input_safeguards.consume_rate_budget(active_session_id)
                if not allowed_budget:
                    await transport.send_event(
                        self.core.server._event(
                            "error",
                            active_session_id,
                            "Rate limit exceeded. Retry in %.2fs." % retry_after_s,
                        )
                    )
                    continue
                if self.core._is_mutation_envelope(envelope) and not self.core.server.feature_profile.world_mutation_allowed():
                    await transport.send_event(
                        self.core.server._event("error", active_session_id, "World mutation is disabled by server profile.")
                    )
                    continue
                if self.core._is_authoring_envelope(envelope):
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "creator_sdk.authoring")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "creator_sdk.authoring", ent_reason)
                        )
                        continue
                    authoring_denial = self.core._authoring_denial_reason(active_session_id)
                    if authoring_denial:
                        await transport.send_event(
                            self.core.server._event("error", active_session_id, authoring_denial)
                        )
                        continue
                client_protocol = str(envelope.get("protocol_version", "")).strip()
                if client_protocol and client_protocol != PROTOCOL_VERSION:
                    await transport.send_event(
                        self.core.server._event(
                            "protocol_mismatch",
                            active_session_id,
                            {
                                "client_protocol_version": client_protocol,
                                "server_protocol_version": PROTOCOL_VERSION,
                                "action": "continue_degraded",
                            },
                        )
                    )
                if envelope.get("type") == "resume_session":
                    requested = str(envelope.get("session_id", "")).strip()
                    allowed_resume, resume_reason = self.core.server.validate_resume_session_target(requested)
                    if allowed_resume:
                        # Discard the ephemeral session created at connection time
                        # and attach this transport to the resumed session instead.
                        ephemeral_id = active_session_id
                        self._ws_sessions.pop(ephemeral_id, None)
                        self.core.server.sessions.pop(ephemeral_id, None)
                        self.core.input_safeguards.clear_session(ephemeral_id)
                        active_session_id = requested
                        self.core.server.mark_session_connected(active_session_id)
                        self._ws_sessions[active_session_id] = transport
                        await transport.send_event(
                            self.core.server._event(
                                "session_resumed",
                                active_session_id,
                                {"session_id": active_session_id, "resumed": True},
                            )
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "auth_state",
                                active_session_id,
                                self.core._build_auth_state_payload(active_session_id),
                            )
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "server_policy",
                                active_session_id,
                                self.core.build_operator_policy_payload(active_session_id),
                            )
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "party_state",
                                active_session_id,
                                self.core.server.build_party_state_payload(active_session_id),
                            )
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "lock_state",
                                active_session_id,
                                self.core._build_lock_state_payload(),
                            )
                        )
                        for event in self.core.server.build_party_presence_sync_events_for_session(active_session_id):
                            target_id = str(event.get("session_id", ""))
                            if target_id == active_session_id:
                                continue
                            target_transport = self._ws_sessions.get(target_id)
                            if target_transport is not None:
                                await target_transport.send_event(event)
                    else:
                        await transport.send_event(
                            self.core.server._event(
                                "error",
                                active_session_id,
                                resume_reason or "Resume rejected",
                            )
                        )
                        for event in self.core.server.prune_expired_shard_sessions():
                            await self._broadcast_ws_event(event)
                    continue
                if envelope.get("type") == "lock_acquire":
                    for event in self.core._handle_lock_acquire_envelope(active_session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_ws_event(event)
                        else:
                            await transport.send_event(event)
                    continue
                if envelope.get("type") == "lock_release":
                    for event in self.core._handle_lock_release_envelope(active_session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_ws_event(event)
                        else:
                            await transport.send_event(event)
                    continue
                if envelope.get("type") == "lock_renew":
                    for event in self.core._handle_lock_renew_envelope(active_session_id, envelope):
                        if event.get("type") == "lock_state_delta":
                            await self._broadcast_ws_event(event)
                        else:
                            await transport.send_event(event)
                    continue

                if envelope.get("type") == "asset_update":
                    events = self.core._handle_asset_update_envelope(active_session_id, envelope)
                    for event in events:
                        if event.get("type") == "asset":
                            await self._broadcast_ws_event(event)
                        else:
                            await transport.send_event(event)
                    continue
                if envelope.get("type") == "lock_status":
                    await transport.send_event(
                        self.core.server._event(
                            "lock_state",
                            active_session_id,
                            self.core._build_lock_state_payload(),
                        )
                    )
                    continue

                raw_command_text = str(envelope.get("command_text", "")).strip()
                command_text = raw_command_text.lower()
                gm_handled, gm_events = self.core._handle_gm_command(active_session_id, raw_command_text)
                if gm_handled:
                    for gm_event in gm_events:
                        await transport.send_event(gm_event)
                    continue
                translated, authoring_error = self.core._translate_authoring_shell_command(active_session_id, command_text)
                if authoring_error:
                    await transport.send_event(
                        self.core.server._event("error", active_session_id, authoring_error)
                    )
                    continue
                if translated is not None:
                    if self.core._is_mutation_envelope(translated) and not self.core.server.feature_profile.world_mutation_allowed():
                        await transport.send_event(
                            self.core.server._event("error", active_session_id, "World mutation is disabled by server profile.")
                        )
                        continue
                    if self.core._is_authoring_envelope(translated):
                        ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "creator_sdk.authoring")
                        if not ent_ok:
                            await transport.send_event(
                                self.core._entitlement_error_event(active_session_id, "creator_sdk.authoring", ent_reason)
                            )
                            continue
                        authoring_denial = self.core._authoring_denial_reason(active_session_id)
                        if authoring_denial:
                            await transport.send_event(
                                self.core.server._event("error", active_session_id, authoring_denial)
                            )
                            continue
                    if translated.get("type") == "lock_acquire":
                        for event in self.core._handle_lock_acquire_envelope(active_session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_ws_event(event)
                            else:
                                await transport.send_event(event)
                        continue
                    if translated.get("type") == "lock_release":
                        for event in self.core._handle_lock_release_envelope(active_session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_ws_event(event)
                            else:
                                await transport.send_event(event)
                        continue
                    if translated.get("type") == "lock_renew":
                        for event in self.core._handle_lock_renew_envelope(active_session_id, translated):
                            if event.get("type") == "lock_state_delta":
                                await self._broadcast_ws_event(event)
                            else:
                                await transport.send_event(event)
                        continue
                    if translated.get("type") == "asset_update":
                        events = self.core._handle_asset_update_envelope(active_session_id, translated)
                        for event in events:
                            if event.get("type") == "asset":
                                await self._broadcast_ws_event(event)
                            else:
                                await transport.send_event(event)
                        continue
                    if translated.get("type") == "lock_status":
                        await transport.send_event(
                            self.core.server._event(
                                "lock_state",
                                active_session_id,
                                self.core._build_lock_state_payload(),
                            )
                        )
                        continue

                if command_text == "blighttest":
                    payload = self.core._build_blight_payload(envelope.get("client_capabilities", {}))
                    await transport.send_event(
                        self.core.server._event("text", active_session_id, payload)
                    )
                    continue
                if command_text == "svgtest":
                    payload = self.core._build_svg_test_payload()
                    await transport.send_event(
                        self.core.server._event("asset", active_session_id, payload)
                    )
                    continue
                if self.core._is_server_policy_command(command_text):
                    await transport.send_event(
                        self.core.server._event(
                            "server_policy",
                            active_session_id,
                            self.core.build_operator_policy_payload(active_session_id),
                        )
                    )
                    continue
                if self.core._is_profile_list_command(command_text):
                    presets = self.core._list_profile_presets()
                    await transport.send_event(
                        self.core.server._event(
                            "profile_presets",
                            active_session_id,
                            self.core.build_profile_presets_payload(),
                        )
                    )
                    if presets:
                        await transport.send_event(
                            self.core.server._event(
                                "text",
                                active_session_id,
                                "Available profiles: %s" % ", ".join(presets),
                            )
                        )
                    else:
                        await transport.send_event(
                            self.core.server._event("text", active_session_id, "No profile presets found.")
                        )
                    continue
                if self.core._is_shard_status_command(command_text):
                    payload = self.core._shard_status_payload()
                    await transport.send_event(
                        self.core.server._event("shard_status", active_session_id, payload)
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
                    await transport.send_event(
                        self.core.server._event("text", active_session_id, summary)
                    )
                    continue
                shard_mode_target, shard_mode_message = self.core._parse_shard_mode_command(raw_command_text)
                if shard_mode_target != "":
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.shard.manage")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.shard.manage", ent_reason)
                        )
                        continue
                    ok, message = self.core._set_shard_mode(active_session_id, shard_mode_target, shard_mode_message)
                    await transport.send_event(
                        self.core.server._event("text" if ok else "error", active_session_id, message)
                    )
                    if ok:
                        await self._broadcast_shard_runtime_update(active_session_id)
                    continue
                profile_apply_target = self.core._parse_profile_apply_command(command_text)
                if profile_apply_target != "":
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.profile.apply")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.profile.apply", ent_reason)
                        )
                        continue
                    ok, message = self.core._apply_profile_preset(profile_apply_target)
                    if not ok:
                        await transport.send_event(
                            self.core.server._event("error", active_session_id, message)
                        )
                    else:
                        await transport.send_event(
                            self.core.server._event("text", active_session_id, message)
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "server_policy",
                                active_session_id,
                                self.core.build_operator_policy_payload(active_session_id),
                            )
                        )
                    continue
                if self.core._is_world_effects_list_command(command_text):
                    payload = self.core._world_effects_status_payload()
                    await transport.send_event(
                        self.core.server._event("world_effects_providers", active_session_id, payload)
                    )
                    await transport.send_event(
                        self.core.server._event(
                            "text",
                            active_session_id,
                            "World-effects providers: %s" % ", ".join(payload["available_providers"]),
                        )
                    )
                    continue
                if self.core._is_world_effects_status_command(command_text):
                    payload = self.core._world_effects_status_payload()
                    await transport.send_event(
                        self.core.server._event("world_effects_status", active_session_id, payload)
                    )
                    await transport.send_event(
                        self.core.server._event(
                            "text",
                            active_session_id,
                            "World-effects mode=%s provider=%s"
                            % (payload["mode"], payload["active_provider"]),
                        )
                    )
                    continue
                effects_use_target = self.core._parse_world_effects_use_command(command_text)
                if effects_use_target != "":
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.world_effects.manage")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.world_effects.manage", ent_reason)
                        )
                        continue
                    ok, message = self.core._set_world_effects_provider(active_session_id, effects_use_target)
                    event_type = "text" if ok else "error"
                    await transport.send_event(
                        self.core.server._event(event_type, active_session_id, message)
                    )
                    if ok:
                        await transport.send_event(
                            self.core.server._event(
                                "world_effects_status",
                                active_session_id,
                                self.core._world_effects_status_payload(),
                            )
                        )
                        await transport.send_event(
                            self.core.server._event(
                                "server_policy",
                                active_session_id,
                                self.core.build_operator_policy_payload(active_session_id),
                            )
                        )
                    continue

                if self.core._is_audit_stale_refs_command(command_text):
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.audit.stale_refs")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.audit.stale_refs", ent_reason)
                        )
                    else:
                        result = self.core._run_stale_ref_audit()
                        await transport.send_event(
                            self.core.server._event("audit_result", active_session_id, result)
                        )
                        summary = (
                            result.get("error")
                            or (
                                f"Audit clean: {result['root']}"
                                if result.get("clean")
                                else f"Audit found {result['error_count']} error(s), {result['warn_count']} warning(s) in {result['root']}"
                            )
                        )
                        await transport.send_event(
                            self.core.server._event("text", active_session_id, summary)
                        )
                    continue
                if self.core._is_audit_boot_warnings_command(command_text):
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.audit.boot_warnings")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.audit.boot_warnings", ent_reason)
                        )
                    else:
                        result = self.core._run_boot_warning_audit()
                        await transport.send_event(
                            self.core.server._event("audit_result", active_session_id, result)
                        )
                        summary = (
                            "Boot warnings: clean (0)"
                            if result.get("clean")
                            else f"Boot warnings: {result.get('warning_count', 0)} record(s), {len(result.get('codes', {}))} code(s)"
                        )
                        await transport.send_event(
                            self.core.server._event("text", active_session_id, summary)
                        )
                    continue
                if self.core._is_audit_shard_command(command_text):
                    ent_ok, ent_reason = self.core._check_session_entitlement(active_session_id, "operator.shard.manage")
                    if not ent_ok:
                        await transport.send_event(
                            self.core._entitlement_error_event(active_session_id, "operator.shard.manage", ent_reason)
                        )
                    else:
                        result = self.core._run_shard_runtime_audit()
                        await transport.send_event(
                            self.core.server._event("audit_result", active_session_id, result)
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
                        await transport.send_event(
                            self.core.server._event("text", active_session_id, summary)
                        )
                    continue

                envelope["session_id"] = active_session_id
                cmd_ok, cmd_reason = self.core.input_safeguards.check_command_text(str(envelope.get("command_text", "")))
                if not cmd_ok:
                    await transport.send_event(
                        self.core.server._event("error", active_session_id, cmd_reason)
                    )
                    continue
                events = self.core.server.execute_command_envelope(envelope)
                for event in events:
                    target_id = event.get("session_id")
                    if target_id == "*" or target_id == "broadcast":
                        await self._broadcast_ws_event(event)
                    elif target_id and target_id != active_session_id and target_id in self._ws_sessions:
                        await self._ws_sessions[target_id].send_event(event)
                    else:
                        await transport.send_event(event)
        finally:
            self.core.server.mark_session_disconnected(active_session_id)
            await self._release_session_locks(active_session_id)
            for event in self.core.server.build_party_presence_sync_events_for_session(active_session_id):
                target_id = str(event.get("session_id", ""))
                if target_id == active_session_id:
                    continue
                target_transport = self._ws_sessions.get(target_id)
                if target_transport is not None:
                    await target_transport.send_event(event)
            self.core.input_safeguards.clear_session(active_session_id)
            self._ws_sessions.pop(active_session_id, None)
            active_ids = set(self._ws_sessions.keys())
            self.core.input_safeguards.evict_stale_sessions(active_ids)
            self.core._gm_auth_failures.pop(active_session_id, None)
            self.core._gm_auth_cooldown_until.pop(active_session_id, None)
        return active_session_id

    async def _broadcast_ws_event(self, event: dict[str, Any]) -> None:
        dead: list[str] = []
        for session_id, transport in self._ws_sessions.items():
            try:
                await transport.send_event(event)
            except Exception:
                dead.append(session_id)
        for session_id in dead:
            self._ws_sessions.pop(session_id, None)

    async def _broadcast_shard_runtime_update(self, actor_session_id: str) -> None:
        announcement = self.core._build_shard_mode_announcement(actor_session_id)
        status_payload = self.core._shard_status_payload()
        for target_session_id, target_transport in list(self._ws_sessions.items()):
            await target_transport.send_event(
                self.core.server._event("shard_status", target_session_id, status_payload)
            )
            if target_session_id != actor_session_id:
                await target_transport.send_event(
                    self.core.server._event("text", target_session_id, announcement)
                )
            await target_transport.send_event(
                self.core.server._event(
                    "server_policy",
                    target_session_id,
                    self.core.build_operator_policy_payload(target_session_id),
                )
            )

    async def _release_session_locks(self, session_id: str) -> None:
        for delta in self.core.assets.release_locks_for_session(session_id):
            await self._broadcast_ws_event(
                self.core.server._event(
                    "lock_state_delta",
                    session_id,
                    delta,
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC WebSocket JSON-envelope MUD server")
    parser.add_argument("--config", default="server/config/server_config.json", help="Master server config JSON path.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--save", "-s", default=None)
    parser.add_argument("--asset-db", default=None)
    parser.add_argument("--content-set", required=True, help="Content-set directory or manifest path.")
    args = parser.parse_args()
    config_payload = load_server_config(args.config)
    settings = resolve_server_settings(
        "ws",
        config_payload,
        args.host,
        args.port,
        args.save,
        args.asset_db,
        args.config,
    )

    app = JsonWebSocketMudServer(
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
    for warning in app.core.server.boot_warnings:
        print("Feature profile warning:", warning)
    print(
        "Effective server settings:",
        json.dumps(
            {
                "transport": "ws",
                "config_path": settings.config_path,
                "host": settings.host,
                "port": settings.port,
                "save_file": settings.save_file,
                "asset_db": settings.asset_db,
                "content_set": app.core.effective_settings()["content_set"],
                "feature_profile_modes": {
                    "combat": app.core.server.feature_profile.combat_mode,
                    "weather": app.core.server.feature_profile.weather_mode,
                    "world_effects": app.core.server.feature_profile.world_effects_mode,
                    "authoring": app.core.server.feature_profile.authoring_mode,
                    "world_mutation": app.core.server.feature_profile.world_mutation_mode,
                    "mods": app.core.server.feature_profile.mods_mode,
                },
                "require_character_creation": bool(app.core.server.require_character_creation),
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
