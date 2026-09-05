import asyncio
import json
import unittest
from typing import Any

from poc_server import JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer
from tests.fixtures import FANTASY_FRONTIER


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


class TestTransportStartupDiagnosticsParity(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_hello_contains_startup_diagnostics_contract(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            hello = json.loads((await reader.readline()).decode("utf-8"))
            payload = hello.get("payload", {})
            startup = payload.get("startup_diagnostics", {})
            self.assertEqual("hello", hello.get("type"))
            self.assertIsInstance(startup, dict)
            self.assertIn("warning_count", startup)
            self.assertIn("warning_codes", startup)
            self.assertIn("boot_warning_fail_codes", startup)
            self.assertNotIn("content_root", startup)
            self.assertNotIn("fixture_refresh_marker", startup)
            self.assertIsInstance(startup.get("warning_count"), int)
            self.assertIsInstance(startup.get("warning_codes"), dict)
            self.assertIsInstance(startup.get("boot_warning_fail_codes"), list)
        finally:
            writer.write(b'{"type":"disconnect"}\n')
            await writer.drain()
            await reader.readline()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_ws_hello_contains_startup_diagnostics_contract(self) -> None:
        app = JsonWebSocketMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)
        fake_ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(fake_ws)
        finally:
            app.shutdown()

        events = [json.loads(frame) for frame in fake_ws.sent if isinstance(frame, str)]
        hello = events[0]
        payload = hello.get("payload", {})
        startup = payload.get("startup_diagnostics", {})
        self.assertEqual("hello", hello.get("type"))
        self.assertIsInstance(startup, dict)
        self.assertIn("warning_count", startup)
        self.assertIn("warning_codes", startup)
        self.assertIn("boot_warning_fail_codes", startup)
        self.assertNotIn("content_root", startup)
        self.assertNotIn("fixture_refresh_marker", startup)
        self.assertIsInstance(startup.get("warning_count"), int)
        self.assertIsInstance(startup.get("warning_codes"), dict)
        self.assertIsInstance(startup.get("boot_warning_fail_codes"), list)
