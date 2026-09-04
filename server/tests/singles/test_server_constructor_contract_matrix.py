import json
import unittest
from typing import Any

from engine.server.headless_server import HeadlessServer
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


class TestServerConstructorContractMatrix(unittest.IsolatedAsyncioTestCase):
    def test_headless_constructor_honors_entitlement_policy_and_char_creation_flag(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"default_session_grants": ["operator.audit.stale_refs"]},
            require_character_creation=True,
        )
        try:
            self.assertTrue(server.require_character_creation)
            session = server.create_session()
            self.assertIn("operator.audit.stale_refs", session.entitlements)
        finally:
            server.shutdown()

    def test_tcp_constructor_contract_surface(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"default_session_grants": ["operator.audit.stale_refs"]},
            require_character_creation=True,
        )
        try:
            settings = app.effective_settings()
            self.assertTrue(settings["require_character_creation"])
            self.assertIn("operator.audit.stale_refs", app.server.entitlement_guard.default_grants)
            policy = app.build_server_policy_payload()
            self.assertTrue(policy["require_character_creation"])
            self.assertIn("operator.audit.stale_refs", policy["entitlement_policy"]["default_session_grants"])
        finally:
            app.shutdown()

    async def test_ws_hello_includes_contract_policy_flags(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"default_session_grants": ["operator.audit.stale_refs"]},
            require_character_creation=True,
        )
        ws = _FakeWebSocket([json.dumps({"type": "disconnect"})])
        try:
            await app._handle_websocket_client(ws)
            parsed = [json.loads(item) for item in ws.sent if isinstance(item, str)]
            hello = parsed[0]
            payload = hello.get("payload", {})
            self.assertEqual("hello", hello.get("type"))
            self.assertIn("server_policy", payload)
            self.assertTrue(payload["server_policy"]["require_character_creation"])
            self.assertIn(
                "operator.audit.stale_refs",
                payload["server_policy"]["entitlement_policy"]["default_session_grants"],
            )
        finally:
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
