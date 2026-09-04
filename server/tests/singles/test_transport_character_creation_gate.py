import asyncio
import json
import unittest
from typing import Any

from poc_server import JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer
from tests.fixtures import FANTASY_FRONTIER


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


class TestTransportCharacterCreationGate(unittest.IsolatedAsyncioTestCase):
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

    async def test_tcp_requires_character_before_gameplay(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            require_character_creation=True,
        )
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await reader.readline()
            await reader.readline()
            await reader.readline()

            writer.write(b"look\n")
            await writer.drain()
            blocked = await self._read_available_events(reader)
            blocked_texts = [str(ev.get("payload", "")) for ev in blocked if ev.get("type") == "text"]
            self.assertTrue(any("No character yet. Use: char create <name>" in text for text in blocked_texts))
            self.assertFalse(any(ev.get("type") == "nearby" for ev in blocked))

            writer.write(b"char create Tester\n")
            await writer.drain()
            created = await self._read_available_events(reader)
            created_texts = [str(ev.get("payload", "")) for ev in created if ev.get("type") == "text"]
            self.assertTrue(any("Character created: Tester" in text for text in created_texts))

            writer.write(b"look\n")
            await writer.drain()
            post_create = await self._read_available_events(reader)
            self.assertTrue(any(ev.get("type") == "nearby" for ev in post_create))
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            app.shutdown()

    async def test_ws_requires_character_before_gameplay(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            require_character_creation=True,
        )
        fake_ws = _FakeWebSocket(
            [
                json.dumps({"type": "command", "command_text": "look"}),
                json.dumps({"type": "command", "command_text": "char create Tester"}),
                json.dumps({"type": "command", "command_text": "look"}),
                json.dumps({"type": "disconnect"}),
            ]
        )
        try:
            await app._handle_websocket_client(fake_ws)
            parsed = [json.loads(item) for item in fake_ws.sent if isinstance(item, str)]

            pre_create_texts: list[str] = []
            post_create_events: list[dict[str, Any]] = []
            saw_create = False
            for event in parsed:
                if event.get("type") == "text":
                    payload = str(event.get("payload", ""))
                    if "Character created: Tester" in payload:
                        saw_create = True
                    elif not saw_create:
                        pre_create_texts.append(payload)
                if saw_create:
                    post_create_events.append(event)

            self.assertTrue(any("No character yet. Use: char create <name>" in text for text in pre_create_texts))
            self.assertTrue(any(ev.get("type") == "nearby" for ev in post_create_events))
        finally:
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
