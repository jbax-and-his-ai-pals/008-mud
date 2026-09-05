import asyncio
import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from typing import Any

from poc_server import JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer
from tests.fixtures import FANTASY_FRONTIER
from tests.singles.snapshot_assertions import assert_snapshot

try:
    import msgpack  # type: ignore
except Exception:  # pragma: no cover
    msgpack = None


class _FakeWebSocket:
    def __init__(self, incoming: list[Any]) -> None:
        self._incoming = list(incoming)
        self.sent: list[Any] = []

    async def recv(self) -> Any:
        if not self._incoming:
            return None
        return self._incoming.pop(0)

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)


class TestTransportParitySnapshots(unittest.IsolatedAsyncioTestCase):
    def _snapshot_path(self, name: str) -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "snapshots", name))

    async def _read_available_events(self, reader: asyncio.StreamReader, max_events: int = 8) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for _ in range(max_events):
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.1)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            events.append(json.loads(line.decode("utf-8")))
        return events

    @staticmethod
    def _protocol_contract_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep protocol events; world simulation is covered by content-set tests."""
        volatile_types = {"nearby", "text", "world_state"}
        return [event for event in events if event.get("type") not in volatile_types]

    def _case_root(self) -> Path:
        root = Path(__file__).resolve().parents[1] / "_tmp" / f"audit_snapshot_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _seed_minimal_content_root(self, root: Path) -> None:
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

    async def test_tcp_json_contract_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            auth_state = json.loads((await reader.readline()).decode("utf-8"))
            lock_state = json.loads((await reader.readline()).decode("utf-8"))

            writer.write(b"profile list\n")
            await writer.drain()
            presets_event = json.loads((await reader.readline()).decode("utf-8"))
            presets_text = json.loads((await reader.readline()).decode("utf-8"))

            payload = {
                "transport": "tcp-json",
                "events": [hello, auth_state, lock_state, presets_event, presets_text],
            }
            assert_snapshot(self, self._snapshot_path("transport_tcp_json_contract.json"), payload)

            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_ws_json_contract_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "command", "command_text": "profile list"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            payload = {
                "transport": "ws-json",
                "events": parsed,
            }
            assert_snapshot(self, self._snapshot_path("transport_ws_json_contract.json"), payload)
        finally:
            app.shutdown()

    async def test_ws_msgpack_contract_snapshot(self) -> None:
        if msgpack is None:
            self.skipTest("msgpack not installed")

        first = msgpack.packb({"type": "command", "command_text": "profile list"}, use_bin_type=True)
        second = msgpack.packb({"type": "disconnect"}, use_bin_type=True)

        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        fake_ws = _FakeWebSocket([first, second])
        try:
            await app._handle_websocket_client(fake_ws)

            decoded: list[dict[str, Any]] = []
            frame_types: list[str] = []
            for frame in fake_ws.sent:
                if isinstance(frame, bytes):
                    frame_types.append("bytes")
                    decoded.append(msgpack.unpackb(frame, raw=False))
                else:
                    frame_types.append("str")
                    decoded.append(json.loads(frame))

            payload = {
                "transport": "ws-msgpack",
                "frame_types": frame_types,
                "events": decoded,
            }
            assert_snapshot(self, self._snapshot_path("transport_ws_msgpack_contract.json"), payload)
        finally:
            app.shutdown()

    async def test_tcp_authoring_policy_denied_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "disabled"
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write((json.dumps({"type": "lock_acquire", "payload": {"asset_id": "contract_asset"}}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_authoring_denied.json"),
                {"transport": "tcp-json", "authoring_mode": "disabled", "events": events},
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_authoring_policy_denied_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "disabled"
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "lock_acquire", "payload": {"asset_id": "contract_asset"}}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_authoring_denied.json"),
                {"transport": "ws-json", "authoring_mode": "disabled", "events": parsed},
            )
        finally:
            app.shutdown()

    async def test_tcp_authoring_policy_allowed_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "all"
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write((json.dumps({"type": "lock_acquire", "payload": {"asset_id": "contract_asset"}}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_authoring_allowed.json"),
                {"transport": "tcp-json", "authoring_mode": "all", "events": events},
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_authoring_policy_allowed_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "all"
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "lock_acquire", "payload": {"asset_id": "contract_asset"}}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_authoring_allowed.json"),
                {"transport": "ws-json", "authoring_mode": "all", "events": parsed},
            )
        finally:
            app.shutdown()

    async def test_tcp_asset_update_policy_denied_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "disabled"
        app.assets.build_svg_test_payload()
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            envelope = {
                "type": "asset_update",
                "payload": {
                    "asset_id": "test_glyph_001",
                    "base_revision": 1,
                    "svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='1' height='1' fill='black'/></svg>",
                    "alt_text": "updated",
                },
            }
            writer.write((json.dumps(envelope) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(self, self._snapshot_path("transport_tcp_asset_update_denied.json"), {"events": events})
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_asset_update_policy_denied_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "disabled"
        app.core.assets.build_svg_test_payload()
        fake_ws = _FakeWebSocket([
            json.dumps({
                "type": "asset_update",
                "payload": {
                    "asset_id": "test_glyph_001",
                    "base_revision": 1,
                    "svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='1' height='1' fill='black'/></svg>",
                    "alt_text": "updated",
                },
            }),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(self, self._snapshot_path("transport_ws_asset_update_denied.json"), {"events": parsed})
        finally:
            app.shutdown()

    async def test_tcp_asset_update_allowed_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "all"
        app.assets.build_svg_test_payload()
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write((json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}) + "\n").encode("utf-8"))
            await writer.drain()
            await self._read_available_events(reader)
            envelope = {
                "type": "asset_update",
                "payload": {
                    "asset_id": "test_glyph_001",
                    "base_revision": 1,
                    "svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='1' height='1' fill='white'/></svg>",
                    "alt_text": "allowed update",
                },
            }
            writer.write((json.dumps(envelope) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(self, self._snapshot_path("transport_tcp_asset_update_allowed.json"), {"events": events})
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_asset_update_allowed_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "all"
        app.core.assets.build_svg_test_payload()
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}),
            json.dumps({
                "type": "asset_update",
                "payload": {
                    "asset_id": "test_glyph_001",
                    "base_revision": 1,
                    "svg": "<svg xmlns='http://www.w3.org/2000/svg'><rect width='1' height='1' fill='white'/></svg>",
                    "alt_text": "allowed update",
                },
            }),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(self, self._snapshot_path("transport_ws_asset_update_allowed.json"), {"events": parsed})
        finally:
            app.shutdown()

    async def test_tcp_asset_update_malformed_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "all"
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write((json.dumps({"type": "asset_update", "payload": "not-an-object"}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(self, self._snapshot_path("transport_tcp_asset_update_malformed.json"), {"events": events})
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_asset_update_malformed_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "all"
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "asset_update", "payload": "not-an-object"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(self, self._snapshot_path("transport_ws_asset_update_malformed.json"), {"events": parsed})
        finally:
            app.shutdown()

    async def test_tcp_disconnect_releases_locks_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "all"
        app.assets.build_svg_test_payload()
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader_a, writer_a = await asyncio.open_connection(host, port)
        reader_b, writer_b = await asyncio.open_connection(host, port)
        try:
            await reader_a.readline(); await reader_a.readline(); await reader_a.readline()
            await reader_b.readline(); await reader_b.readline(); await reader_b.readline()
            writer_a.write((json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}) + "\n").encode("utf-8"))
            await writer_a.drain()
            await self._read_available_events(reader_a)
            await self._read_available_events(reader_b)

            writer_a.close()
            await writer_a.wait_closed()
            events_b = await self._read_available_events(reader_b, max_events=10)
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_disconnect_releases_locks.json"),
                {"events": events_b},
            )
        finally:
            writer_b.close(); await writer_b.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_disconnect_releases_locks_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "all"
        app.core.assets.build_svg_test_payload()
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            deltas = [evt for evt in parsed if evt.get("type") == "lock_state_delta"]
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_disconnect_releases_locks.json"),
                {"events": deltas},
            )
        finally:
            app.shutdown()

    async def test_tcp_lock_status_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.server.feature_profile.authoring_mode = "all"
        app.assets.build_svg_test_payload()
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write((json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}) + "\n").encode("utf-8"))
            await writer.drain()
            await self._read_available_events(reader)
            writer.write((json.dumps({"type": "lock_status"}) + "\n").encode("utf-8"))
            await writer.drain()
            events = await self._read_available_events(reader)
            state_events = [evt for evt in events if evt.get("type") == "lock_state"]
            assert_snapshot(self, self._snapshot_path("transport_tcp_lock_status.json"), {"events": state_events})
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_lock_status_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        app.core.server.feature_profile.authoring_mode = "all"
        app.core.assets.build_svg_test_payload()
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "lock_acquire", "payload": {"asset_id": "test_glyph_001"}}),
            json.dumps({"type": "lock_status"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            state_events = [evt for evt in parsed if evt.get("type") == "lock_state"]
            assert_snapshot(self, self._snapshot_path("transport_ws_lock_status.json"), {"events": state_events})
        finally:
            app.shutdown()

    async def test_tcp_world_effects_custom_policy_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)

        class _TestEffectsProvider:
            mode = "custom"
            provider_id = "contract.effects.sample"

            def tick(self, server_ref, session_id: str):
                return []

        app.server.feature_profile.world_effects_mode = "custom"
        app.server.feature_profile.raw = {"world_effects": {"mode": "custom", "provider_id": "contract.effects.sample"}}
        app.server.register_world_effects_provider("contract.effects.sample", _TestEffectsProvider())

        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_world_effects_custom_policy.json"),
                {"transport": "tcp-json", "hello": hello},
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_world_effects_custom_policy_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)

        class _TestEffectsProvider:
            mode = "custom"
            provider_id = "contract.effects.sample"

            def tick(self, server_ref, session_id: str):
                return []

        app.core.server.feature_profile.world_effects_mode = "custom"
        app.core.server.feature_profile.raw = {"world_effects": {"mode": "custom", "provider_id": "contract.effects.sample"}}
        app.core.server.register_world_effects_provider("contract.effects.sample", _TestEffectsProvider())
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            hello = parsed[0] if parsed else {}
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_world_effects_custom_policy.json"),
                {"transport": "ws-json", "hello": hello},
            )
        finally:
            app.shutdown()

    async def test_tcp_world_effects_status_command_snapshot(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            session_default_capabilities=["authoring.gm"],
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write(b"effects status\n")
            await writer.drain()
            events = await self._read_available_events(reader)
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_world_effects_status.json"),
                {"events": events},
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_world_effects_status_command_snapshot(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            session_default_capabilities=["authoring.gm"],
        )
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "command", "command_text": "effects status"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            events = [evt for evt in parsed if evt.get("type") in {"world_effects_status", "text"}]
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_world_effects_status.json"),
                {"events": events},
            )
        finally:
            app.shutdown()

    async def test_tcp_operator_catalog_entitlement_filtered_snapshot(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_operator_catalog_entitlement_filtered.json"),
                {"transport": "tcp-json", "hello": hello},
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_operator_catalog_entitlement_filtered_snapshot(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
        )
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            hello = parsed[0] if parsed else {}
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_operator_catalog_entitlement_filtered.json"),
                {"transport": "ws-json", "hello": hello},
            )
        finally:
            app.shutdown()

    async def test_tcp_audit_stale_refs_snapshot(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            session_default_entitlements=["operator.audit.stale_refs"],
            entitlement_policy={"gates": {"operator.audit.stale_refs": {"requires": ["operator.audit.stale_refs"]}}},
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline(); await reader.readline(); await reader.readline()
            writer.write(b"audit stale-refs\n")
            await writer.drain()
            events = await self._read_available_events(reader)
            root_value = str(app.server.world.content_root)
            for event in events:
                payload = event.get("payload", {})
                if isinstance(payload, dict) and "root" in payload:
                    payload["root"] = "<content_root>"
                elif isinstance(payload, str):
                    event["payload"] = payload.replace(root_value, "<content_root>")
            assert_snapshot(self, self._snapshot_path("transport_tcp_audit_stale_refs.json"), {"events": events})
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_audit_stale_refs_snapshot(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            session_default_entitlements=["operator.audit.stale_refs"],
            entitlement_policy={"gates": {"operator.audit.stale_refs": {"requires": ["operator.audit.stale_refs"]}}},
        )
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "command", "command_text": "audit stale-refs"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            events = [evt for evt in parsed if evt.get("type") in {"audit_result", "text"}]
            root_value = str(app.core.server.world.content_root)
            for event in events:
                payload = event.get("payload", {})
                if isinstance(payload, dict) and "root" in payload:
                    payload["root"] = "<content_root>"
                elif isinstance(payload, str):
                    event["payload"] = payload.replace(root_value, "<content_root>")
            assert_snapshot(self, self._snapshot_path("transport_ws_audit_stale_refs.json"), {"events": events})
        finally:
            app.shutdown()

    async def test_tcp_session_resume_contract_snapshot(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER, require_character_creation=True)
        prior = app.server.create_session()
        prior_id = prior.session_id
        app.server.execute_command(prior_id, "char create SnapshotTester")
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            await reader.readline()
            await reader.readline()
            writer.write((json.dumps({"type": "resume_session", "session_id": prior_id}) + "\n").encode("utf-8"))
            await writer.drain()
            resume_events = await self._read_available_events(reader, max_events=12)
            writer.write(b"look\n")
            await writer.drain()
            post_resume_events = await self._read_available_events(reader, max_events=12)
            assert_snapshot(
                self,
                self._snapshot_path("transport_tcp_session_resume_contract.json"),
                {
                    "transport": "tcp-json",
                    "hello": hello,
                    "resume_events": resume_events,
                    "post_resume_events": self._protocol_contract_events(post_resume_events),
                },
            )
        finally:
            writer.close(); await writer.wait_closed(); server.close(); await server.wait_closed(); app.shutdown()

    async def test_ws_session_resume_contract_snapshot(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER, require_character_creation=True)
        prior = app.core.server.create_session()
        prior_id = prior.session_id
        app.core.server.execute_command(prior_id, "char create SnapshotTester")
        fake_ws = _FakeWebSocket([
            json.dumps({"type": "resume_session", "session_id": prior_id}),
            json.dumps({"type": "command", "command_text": "look"}),
            json.dumps({"type": "disconnect"}),
        ])
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]
            assert_snapshot(
                self,
                self._snapshot_path("transport_ws_session_resume_contract.json"),
                {
                    "transport": "ws-json",
                    "events": self._protocol_contract_events(parsed),
                },
            )
        finally:
            app.shutdown()


if __name__ == "__main__":
    unittest.main()

