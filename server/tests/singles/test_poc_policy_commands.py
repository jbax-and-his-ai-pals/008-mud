import asyncio
import json
import os
import shutil
import tempfile
import unittest
import uuid
from typing import Any
from pathlib import Path

from poc_server import JsonLineMudServer as _JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer as _JsonWebSocketMudServer
from tests.fixtures import FANTASY_FRONTIER


class JsonLineMudServer(_JsonLineMudServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, content_set_path=FANTASY_FRONTIER, **kwargs)


class JsonWebSocketMudServer(_JsonWebSocketMudServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, content_set_path=FANTASY_FRONTIER, **kwargs)


class _FakeWebSocket:
    def __init__(self, incoming: list[str]) -> None:
        self._incoming = list(incoming)
        self.sent: list[Any] = []

    async def recv(self) -> Any:
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)


class _InteractiveFakeWebSocket:
    def __init__(self) -> None:
        self._incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.sent: list[Any] = []

    async def recv(self) -> Any:
        return await self._incoming.get()

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)

    async def push_json(self, payload: dict[str, Any]) -> None:
        await self._incoming.put(json.dumps(payload))

    async def push_disconnect(self) -> None:
        await self._incoming.put(json.dumps({"type": "disconnect"}))


class TestPocPolicyCommands(unittest.IsolatedAsyncioTestCase):
    def _case_root(self) -> Path:
        root = Path(__file__).resolve().parents[1] / "_tmp" / f"audit_policy_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _seed_minimal_data_root(self, root: Path) -> None:
        for rel in ("items", "npcs", "regions", "quests", "campaigns"):
            (root / rel).mkdir(parents=True, exist_ok=True)
        (root / "quests" / "quests.json").write_text("{}", encoding="utf-8")
        (root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"exits": {}}}}), encoding="utf-8"
        )
        (root / "items" / "base.json").write_text(
            json.dumps({"item_ok": {"type": "Item", "name": "ok", "description": "ok", "properties": {}}}),
            encoding="utf-8",
        )
        (root / "npcs" / "base.json").write_text(
            json.dumps({"npc_ok": {"name": "ok", "faction": "friendly"}}), encoding="utf-8"
        )

    async def test_ws_auth_state_hides_entitlements_when_authz_detail_minimal(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["creator_sdk.authoring"],
            session_authz_detail_level="minimal",
        )
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        hello = parsed_events[0].get("payload", {})
        auth_state = parsed_events[1].get("payload", {})
        self.assertNotIn("session_entitlements", hello.get("auth_state", {}))
        self.assertNotIn("session_entitlements", hello.get("server_policy", {}))
        self.assertNotIn("session_entitlements", auth_state)

    async def test_ws_hello_and_auth_state_include_session_entitlements(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["creator_sdk.authoring", "operator.profile.apply"],
        )
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        hello = parsed_events[0]
        auth_state = parsed_events[1]
        hello_auth = hello.get("payload", {}).get("auth_state", {})
        hello_policy = hello.get("payload", {}).get("server_policy", {})
        auth_payload = auth_state.get("payload", {})
        self.assertEqual("hello", hello.get("type"))
        self.assertEqual("auth_state", auth_state.get("type"))
        self.assertEqual(
            ["creator_sdk.authoring", "operator.profile.apply"],
            hello_auth.get("session_entitlements", []),
        )
        self.assertEqual(
            ["creator_sdk.authoring", "operator.profile.apply"],
            hello_policy.get("session_entitlements", []),
        )
        self.assertEqual(
            ["creator_sdk.authoring", "operator.profile.apply"],
            auth_payload.get("session_entitlements", []),
        )

    async def test_ws_profile_apply_requires_entitlement_gate(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            entitlement_policy={"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "profile apply static_world"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(error_events)
        self.assertTrue(any("operator.profile.apply" in str(ev.get("payload", "")) for ev in error_events))

    async def test_ws_audit_stale_refs_requires_entitlement_gate(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            entitlement_policy={"gates": {"operator.audit.stale_refs": {"requires": ["operator.audit.stale_refs"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "audit stale-refs"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(error_events)
        self.assertTrue(any("operator.audit.stale_refs" in str(ev.get("payload", "")) for ev in error_events))

    async def test_ws_audit_stale_refs_emits_audit_result_when_entitled(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.audit.stale_refs"],
            entitlement_policy={"gates": {"operator.audit.stale_refs": {"requires": ["operator.audit.stale_refs"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "audit stale-refs"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        result_events = [event for event in parsed_events if event.get("type") == "audit_result"]
        self.assertTrue(result_events)
        payload = result_events[-1].get("payload", {})
        self.assertEqual("stale_refs", payload.get("audit"))
        self.assertIn("issues", payload)
        self.assertEqual(0, int(payload.get("error_count", -1)))
        self.assertTrue(bool(payload.get("clean", False)))

    async def test_ws_audit_boot_warnings_emits_audit_result_when_entitled(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.audit.boot_warnings"],
            entitlement_policy={"gates": {"operator.audit.boot_warnings": {"requires": ["operator.audit.boot_warnings"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "audit boot-warnings"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        result_events = [event for event in parsed_events if event.get("type") == "audit_result"]
        self.assertTrue(result_events)
        payload = result_events[-1].get("payload", {})
        self.assertEqual("boot_warnings", payload.get("audit"))
        self.assertIn("warning_count", payload)
        self.assertIn("codes", payload)

    async def test_ws_audit_shard_runtime_emits_audit_result_when_entitled(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.shard.manage"],
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "audit shard"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        result_events = [event for event in parsed_events if event.get("type") == "audit_result"]
        self.assertTrue(result_events)
        payload = result_events[-1].get("payload", {})
        self.assertEqual("shard_runtime", payload.get("audit"))
        self.assertIn("diagnostics", payload)
        self.assertEqual("persistent_shard", payload.get("diagnostics", {}).get("world_mode"))

    async def test_ws_operator_catalog_filters_entitlement_gated_actions(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            entitlement_policy={"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
        )
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        hello = parsed_events[0]
        domains = hello.get("payload", {}).get("operator_catalog", {}).get("domains", {})
        profile_actions = domains.get("Profiles", [])
        self.assertIn("List Profiles", profile_actions)
        self.assertNotIn("Apply Selected", profile_actions)

    async def test_ws_operator_catalog_omits_authoring_domain_when_disabled(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json")
        app.core.server.feature_profile.authoring_mode = "disabled"
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        hello = parsed_events[0]
        domains = hello.get("payload", {}).get("operator_catalog", {}).get("domains", {})
        self.assertNotIn("Authoring", domains)

    async def test_ws_operator_catalog_omits_world_effects_domain_when_disabled(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json")
        app.core.server.feature_profile.world_effects_mode = "disabled"
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        hello = parsed_events[0]
        domains = hello.get("payload", {}).get("operator_catalog", {}).get("domains", {})
        self.assertNotIn("World Effects", domains)

    async def test_ws_shard_mode_requires_entitlement_gate(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "shard mode freeze Maintenance window"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(error_events)
        self.assertTrue(any("operator.shard.manage" in str(ev.get("payload", "")) for ev in error_events))

    async def test_ws_shard_mode_updates_policy_when_entitled(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.shard.manage"],
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "shard mode maintenance Rolling restart"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        shard_events = [event for event in parsed_events if event.get("type") == "shard_status"]
        self.assertTrue(shard_events)
        self.assertEqual("maintenance", shard_events[-1].get("payload", {}).get("state"))
        self.assertIn("diagnostics", shard_events[-1].get("payload", {}))
        policy_events = [event for event in parsed_events if event.get("type") == "server_policy"]
        self.assertTrue(policy_events)
        self.assertEqual(
            "maintenance",
            policy_events[-1].get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("runtime_state"),
        )

    async def test_tcp_profile_commands_emit_events(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.profile.apply"],
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            auth_state = json.loads((await reader.readline()).decode("utf-8"))
            lock_state = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("hello", hello.get("type"))
            self.assertEqual("auth_state", auth_state.get("type"))
            self.assertEqual("lock_state", lock_state.get("type"))
            hello_payload = hello.get("payload", {})
            self.assertIn("operator_catalog", hello_payload)
            self.assertIn("domains", hello_payload.get("operator_catalog", {}))
            self.assertIn("startup_diagnostics", hello_payload)
            self.assertEqual(["operator.profile.apply"], hello_payload.get("auth_state", {}).get("session_entitlements", []))
            self.assertEqual(["operator.profile.apply"], hello_payload.get("server_policy", {}).get("session_entitlements", []))
            self.assertEqual(["operator.profile.apply"], auth_state.get("payload", {}).get("session_entitlements", []))

            writer.write(b"profile list\n")
            await writer.drain()
            list_structured_event = json.loads((await reader.readline()).decode("utf-8"))
            list_text_event = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("profile_presets", list_structured_event.get("type"))
            presets_payload = list_structured_event.get("payload", {})
            self.assertIn("presets", presets_payload)
            self.assertEqual("text", list_text_event.get("type"))
            self.assertIn("Available profiles:", str(list_text_event.get("payload", "")))

            writer.write(b"profile apply static_world\n")
            await writer.drain()
            apply_text = json.loads((await reader.readline()).decode("utf-8"))
            apply_policy = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("text", apply_text.get("type"))
            self.assertIn("Profile applied", str(apply_text.get("payload", "")))
            self.assertEqual("server_policy", apply_policy.get("type"))
            payload = apply_policy.get("payload", {})
            self.assertEqual(
                "readonly",
                payload.get("server_policy", {}).get("profile_modes", {}).get("world_mutation"),
            )
            self.assertIn("operator_catalog", payload)
            self.assertIn("startup_diagnostics", payload)

            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            goodbye = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("goodbye", goodbye.get("type"))
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_shard_mode_updates_policy_when_entitled(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.shard.manage"],
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        follower_reader, follower_writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()
            await follower_reader.readline()
            await follower_reader.readline()
            await follower_reader.readline()
            writer.write(b"shard mode drain Queue shutdown\n")
            await writer.drain()
            event_a = json.loads((await reader.readline()).decode("utf-8"))
            event_b = json.loads((await reader.readline()).decode("utf-8"))
            event_c = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("text", event_a.get("type"))
            self.assertEqual("shard_status", event_b.get("type"))
            self.assertEqual("drain", event_b.get("payload", {}).get("state"))
            self.assertIn("diagnostics", event_b.get("payload", {}))
            self.assertEqual("server_policy", event_c.get("type"))
            self.assertEqual(
                "drain",
                event_c.get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("runtime_state"),
            )

            follower_event_a = json.loads((await follower_reader.readline()).decode("utf-8"))
            follower_event_b = json.loads((await follower_reader.readline()).decode("utf-8"))
            follower_event_c = json.loads((await follower_reader.readline()).decode("utf-8"))
            self.assertEqual("shard_status", follower_event_a.get("type"))
            self.assertEqual("drain", follower_event_a.get("payload", {}).get("state"))
            self.assertEqual("text", follower_event_b.get("type"))
            self.assertIn("set shard mode to drain", str(follower_event_b.get("payload", "")).lower())
            self.assertEqual("server_policy", follower_event_c.get("type"))
            self.assertEqual(
                "drain",
                follower_event_c.get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("runtime_state"),
            )
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            follower_writer.write(b'{"type":"disconnect"}\n')
            await follower_writer.drain()
            await follower_reader.readline()
            writer.close()
            await writer.wait_closed()
            follower_writer.close()
            await follower_writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_audit_shard_runtime_emits_audit_result_when_entitled(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.shard.manage"],
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()
            writer.write(b"audit shard\n")
            await writer.drain()
            result = json.loads((await reader.readline()).decode("utf-8"))
            summary = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("audit_result", result.get("type"))
            payload = result.get("payload", {})
            self.assertEqual("shard_runtime", payload.get("audit"))
            self.assertIn("diagnostics", payload)
            self.assertEqual("text", summary.get("type"))
            self.assertIn("Shard runtime:", str(summary.get("payload", "")))
            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_late_join_disabled_blocks_new_character_creation_after_start(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {"late_join_policy": "disabled"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", feature_profile_path=profile_path)
            seeded = app.server.create_session()
            app.server.execute_command(seeded.session_id, "char create Seeder")
            server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
            host, port = server.sockets[0].getsockname()[:2]
            reader, writer = await asyncio.open_connection(host, port)
            try:
                hello = json.loads((await reader.readline()).decode("utf-8"))
                await reader.readline()
                await reader.readline()
                self.assertFalse(
                    hello.get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("new_session_admission_enabled")
                )
                writer.write(b"char create Blocked\n")
                await writer.drain()
                command_event = json.loads((await reader.readline()).decode("utf-8"))
                result_event = json.loads((await reader.readline()).decode("utf-8"))
                self.assertEqual("command", command_event.get("type"))
                self.assertEqual("text", result_event.get("type"))
                self.assertIn("cannot join this shard", str(result_event.get("payload", "")).lower())
                writer.write(b"{\"type\":\"disconnect\"}\n")
                await writer.drain()
                await reader.readline()
            finally:
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                app.shutdown()
        finally:
            os.remove(profile_path)

    async def test_tcp_audit_stale_refs_emits_audit_result_when_entitled(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.audit.stale_refs"],
            entitlement_policy={"gates": {"operator.audit.stale_refs": {"requires": ["operator.audit.stale_refs"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()
            writer.write(b"audit stale-refs\n")
            await writer.drain()
            result = json.loads((await reader.readline()).decode("utf-8"))
            summary = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("audit_result", result.get("type"))
            payload = result.get("payload", {})
            self.assertEqual("stale_refs", payload.get("audit"))
            self.assertEqual(0, int(payload.get("error_count", -1)))
            self.assertTrue(bool(payload.get("clean", False)))
            self.assertEqual("text", summary.get("type"))
            self.assertIn("Audit clean", str(summary.get("payload", "")))
            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_audit_boot_warnings_emits_audit_result_when_entitled(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.audit.boot_warnings"],
            entitlement_policy={"gates": {"operator.audit.boot_warnings": {"requires": ["operator.audit.boot_warnings"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()
            writer.write(b"audit boot-warnings\n")
            await writer.drain()
            result = json.loads((await reader.readline()).decode("utf-8"))
            summary = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("audit_result", result.get("type"))
            payload = result.get("payload", {})
            self.assertEqual("boot_warnings", payload.get("audit"))
            self.assertIn("warning_count", payload)
            self.assertIn("codes", payload)
            self.assertEqual("text", summary.get("type"))
            self.assertIn("Boot warnings:", str(summary.get("payload", "")))
            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_auth_state_hides_entitlements_when_authz_detail_minimal(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.profile.apply"],
            session_authz_detail_level="minimal",
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            auth_state = json.loads((await reader.readline()).decode("utf-8"))
            await reader.readline()  # lock_state
            self.assertNotIn("session_entitlements", hello.get("payload", {}).get("auth_state", {}))
            self.assertNotIn("session_entitlements", hello.get("payload", {}).get("server_policy", {}))
            self.assertNotIn("session_entitlements", auth_state.get("payload", {}))
            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_ws_profile_commands_emit_events(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json")
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "profile list"}),
                json.dumps({"type": "command", "command_text": "profile apply static_world"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        self.assertGreaterEqual(len(parsed_events), 5)
        self.assertEqual("hello", parsed_events[0].get("type"))
        self.assertEqual("auth_state", parsed_events[1].get("type"))
        self.assertEqual("lock_state", parsed_events[2].get("type"))
        hello_payload = parsed_events[0].get("payload", {})
        self.assertIn("operator_catalog", hello_payload)
        self.assertIn("domains", hello_payload.get("operator_catalog", {}))
        self.assertIn("startup_diagnostics", hello_payload)

        text_events = [event for event in parsed_events if event.get("type") == "text"]
        self.assertTrue(any("Available profiles:" in str(ev.get("payload", "")) for ev in text_events))
        self.assertTrue(any("Profile applied" in str(ev.get("payload", "")) for ev in text_events))
        profile_events = [event for event in parsed_events if event.get("type") == "profile_presets"]
        self.assertTrue(profile_events)
        self.assertIsInstance(profile_events[-1].get("payload", {}).get("presets"), list)

        policy_events = [event for event in parsed_events if event.get("type") == "server_policy"]
        self.assertTrue(policy_events)
        policy_payload = policy_events[-1].get("payload", {})
        self.assertEqual(
            "readonly",
            policy_payload.get("server_policy", {}).get("profile_modes", {}).get("world_mutation"),
        )
        self.assertIn("operator_catalog", policy_payload)

    async def test_ws_authoring_envelope_blocked_when_authoring_disabled(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json")
        app.core.server.feature_profile.authoring_mode = "disabled"
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_asset"}}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(error_events)
        self.assertTrue(
            any("live authoring is disabled by server profile" in str(ev.get("payload", "")).lower() for ev in error_events)
        )

    async def test_ws_authoring_envelope_allowed_with_gm_capability_bootstrap(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_capabilities=["authoring.gm"],
        )
        app.core.server.feature_profile.authoring_mode = "gm_only"
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_asset"}}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertFalse(
            any("restricted to gm sessions" in str(ev.get("payload", "")).lower() for ev in error_events)
        )
        self.assertFalse(
            any("live authoring is disabled by server profile" in str(ev.get("payload", "")).lower() for ev in error_events)
        )

    async def test_ws_gm_auth_command_grants_authoring_capability(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            gm_auth_token="topsecret",
        )
        app.core.server.feature_profile.authoring_mode = "gm_only"
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "gm auth wrong"}),
                json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_asset_a"}}),
                json.dumps({"type": "command", "command_text": "gm auth topsecret"}),
                json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_asset_b"}}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        text_events = [event for event in parsed_events if event.get("type") == "text"]
        auth_events = [event for event in parsed_events if event.get("type") == "auth_state"]
        self.assertTrue(any("gm auth failed" in str(ev.get("payload", "")).lower() for ev in error_events))
        self.assertTrue(any("restricted to gm sessions" in str(ev.get("payload", "")).lower() for ev in error_events))
        self.assertTrue(any("gm auth granted for this session" in str(ev.get("payload", "")).lower() for ev in text_events))
        self.assertTrue(any(bool(ev.get("payload", {}).get("gm_granted", False)) for ev in auth_events))

    async def test_ws_gm_status_and_deauth_commands(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            gm_auth_token="topsecret",
            session_default_capabilities=["authoring.gm"],
        )
        app.core.server.feature_profile.authoring_mode = "gm_only"
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "gm status"}),
                json.dumps({"type": "command", "command_text": "gm deauth"}),
                json.dumps({"type": "command", "command_text": "gm status"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        text_events = [event for event in parsed_events if event.get("type") == "text"]
        auth_events = [event for event in parsed_events if event.get("type") == "auth_state"]
        self.assertTrue(any("gm session: yes" in str(ev.get("payload", "")).lower() for ev in text_events))
        self.assertTrue(any("gm auth revoked for this session" in str(ev.get("payload", "")).lower() for ev in text_events))
        self.assertTrue(any("gm session: no" in str(ev.get("payload", "")).lower() for ev in text_events))
        self.assertTrue(any(bool(ev.get("payload", {}).get("gm_granted", False)) for ev in auth_events))
        self.assertTrue(any(not bool(ev.get("payload", {}).get("gm_granted", True)) for ev in auth_events))

    async def test_ws_gm_auth_cooldown_after_repeated_failures(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            gm_auth_token="topsecret",
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "gm auth bad1"}),
                json.dumps({"type": "command", "command_text": "gm auth bad2"}),
                json.dumps({"type": "command", "command_text": "gm auth bad3"}),
                json.dumps({"type": "command", "command_text": "gm auth topsecret"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        text_events = [event for event in parsed_events if event.get("type") == "text"]
        auth_events = [event for event in parsed_events if event.get("type") == "auth_state"]
        self.assertTrue(any("gm auth temporarily locked" in str(ev.get("payload", "")).lower() for ev in error_events))
        self.assertFalse(any("gm auth granted for this session" in str(ev.get("payload", "")).lower() for ev in text_events))
        self.assertTrue(any(int(ev.get("payload", {}).get("gm_auth_cooldown_seconds", 0)) > 0 for ev in auth_events))

    async def test_server_policy_includes_auth_policy_payload(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", gm_auth_token="topsecret")
        policy = app.build_server_policy_payload()
        try:
            self.assertIn("auth_policy", policy)
            auth_policy = policy.get("auth_policy", {})
            self.assertTrue(bool(auth_policy.get("gm_auth_configured", False)))
            self.assertEqual("authoring.gm", str(auth_policy.get("gm_capability_name", "")))
            self.assertIn("gm_auth_cooldown_seconds", auth_policy)
            self.assertIn("abuse_policy", policy)
            self.assertIn("max_command_chars", policy.get("abuse_policy", {}))
        finally:
            app.shutdown()

    async def test_tcp_command_length_guard_rejects_oversized_input(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", max_command_chars=16)
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            long_cmd = "look " + ("x" * 64)
            writer.write((json.dumps({"type": "command", "command_text": long_cmd}) + "\n").encode("utf-8"))
            await writer.drain()
            err = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("error", err.get("type"))
            self.assertIn("command too long", str(err.get("payload", "")).lower())
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_ws_rate_limit_guard_blocks_burst_spam(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            command_rate_limit_per_sec=1.0,
            command_burst=2,
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "look"}),
                json.dumps({"type": "command", "command_text": "look"}),
                json.dumps({"type": "command", "command_text": "look"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(any("rate limit exceeded" in str(ev.get("payload", "")).lower() for ev in error_events))

    async def test_ws_world_effects_provider_commands_require_gm(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json")
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "effects use builtin.world_effects.default"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        error_events = [event for event in parsed_events if event.get("type") == "error"]
        self.assertTrue(any("require a gm session" in str(ev.get("payload", "")).lower() for ev in error_events))

    async def test_ws_world_effects_provider_switch_emits_status_and_policy(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_capabilities=["authoring.gm"],
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "effects providers"}),
                json.dumps({"type": "command", "command_text": "effects use disabled.world_effects"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()
        parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
        providers_events = [event for event in parsed_events if event.get("type") == "world_effects_providers"]
        status_events = [event for event in parsed_events if event.get("type") == "world_effects_status"]
        policy_events = [event for event in parsed_events if event.get("type") == "server_policy"]
        self.assertTrue(providers_events)
        self.assertTrue(status_events)
        self.assertTrue(policy_events)
        self.assertEqual(
            "disabled",
            policy_events[-1].get("payload", {}).get("server_policy", {}).get("profile_modes", {}).get("world_effects"),
        )

    async def test_ws_late_join_disabled_blocks_new_character_creation_after_start(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {"late_join_policy": "disabled"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", feature_profile_path=profile_path)
            seeded = app.core.server.create_session(player_id="seeded_ws_player")
            app.core.server.execute_command(seeded.session_id, "char create Seeder")
            fake_ws = _FakeWebSocket(
                [
                    json.dumps({"type": "command", "command_text": "char create Blocked"}),
                    json.dumps({"type": "disconnect"}),
                ]
            )
            try:
                await app._handle_websocket_client(fake_ws)
            finally:
                app.shutdown()
            parsed_events = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            hello = parsed_events[0]
            self.assertFalse(
                hello.get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("new_session_admission_enabled")
            )
            text_events = [event for event in parsed_events if event.get("type") == "text"]
            self.assertTrue(text_events)
            self.assertIn("cannot join this shard", str(text_events[-1].get("payload", "")).lower())
        finally:
            os.remove(profile_path)

    async def test_ws_shard_mode_broadcasts_status_and_policy_to_other_sessions(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_entitlements=["operator.shard.manage"],
            entitlement_policy={"gates": {"operator.shard.manage": {"requires": ["operator.shard.manage"]}}},
        )
        leader_ws = _InteractiveFakeWebSocket()
        follower_ws = _InteractiveFakeWebSocket()
        leader_task = asyncio.create_task(app._handle_websocket_client(leader_ws))
        follower_task = asyncio.create_task(app._handle_websocket_client(follower_ws))
        try:
            await asyncio.sleep(0.05)
            await leader_ws.push_json({"type": "command", "command_text": "shard mode drain Queue shutdown"})
            await asyncio.sleep(0.05)

            leader_events = [json.loads(item) for item in leader_ws.sent if isinstance(item, str)]
            follower_events = [json.loads(item) for item in follower_ws.sent if isinstance(item, str)]

            leader_status = [event for event in leader_events if event.get("type") == "shard_status"]
            self.assertTrue(leader_status)
            self.assertEqual("drain", leader_status[-1].get("payload", {}).get("state"))

            follower_status = [event for event in follower_events if event.get("type") == "shard_status"]
            follower_text = [event for event in follower_events if event.get("type") == "text"]
            follower_policy = [event for event in follower_events if event.get("type") == "server_policy"]
            self.assertTrue(follower_status)
            self.assertEqual("drain", follower_status[-1].get("payload", {}).get("state"))
            self.assertTrue(any("set shard mode to drain" in str(event.get("payload", "")).lower() for event in follower_text))
            self.assertTrue(follower_policy)
            self.assertEqual(
                "drain",
                follower_policy[-1].get("payload", {}).get("server_policy", {}).get("shard_policy", {}).get("runtime_state"),
            )
        finally:
            await leader_ws.push_disconnect()
            await follower_ws.push_disconnect()
            await asyncio.wait_for(leader_task, timeout=1.0)
            await asyncio.wait_for(follower_task, timeout=1.0)
            app.shutdown()

    async def test_tcp_world_effects_provider_commands_require_gm(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json")
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write(b"effects use builtin.world_effects.default\n")
            await writer.drain()
            denied = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("error", denied.get("type"))
            self.assertIn("require a gm session", str(denied.get("payload", "")).lower())

            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            goodbye = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("goodbye", goodbye.get("type"))
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_tcp_world_effects_provider_switch_emits_status_and_policy(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            session_default_capabilities=["authoring.gm"],
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write(b"effects providers\n")
            await writer.drain()
            providers_event = json.loads((await reader.readline()).decode("utf-8"))
            providers_text = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("world_effects_providers", providers_event.get("type"))
            self.assertEqual("text", providers_text.get("type"))
            self.assertIn("World-effects providers", str(providers_text.get("payload", "")))

            writer.write(b"effects use disabled.world_effects\n")
            await writer.drain()
            switch_text = json.loads((await reader.readline()).decode("utf-8"))
            status_event = json.loads((await reader.readline()).decode("utf-8"))
            policy_event = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("text", switch_text.get("type"))
            self.assertEqual("world_effects_status", status_event.get("type"))
            self.assertEqual("server_policy", policy_event.get("type"))
            self.assertEqual(
                "disabled",
                policy_event.get("payload", {}).get("server_policy", {}).get("profile_modes", {}).get("world_effects"),
            )

            writer.write(b"{\"type\":\"disconnect\"}\n")
            await writer.drain()
            goodbye = json.loads((await reader.readline()).decode("utf-8"))
            self.assertEqual("goodbye", goodbye.get("type"))
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
