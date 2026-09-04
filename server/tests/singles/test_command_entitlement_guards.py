import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestCommandEntitlementGuards(unittest.TestCase):
    def _create_character(self, server: HeadlessServer, session_id: str) -> None:
        server.execute_command(session_id, "char create EntitlementTester")

    def test_debug_world_command_denied_without_entitlement(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            server.entitlement_guard.gates = {
                "operator.world.debug": {"requires": ["operator.world.debug"]},
            }
            session = server.create_session(player_id="entitlement_test_player")
            self._create_character(server, session.session_id)
            events = server.execute_command(session.session_id, "settime day")
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("permission" in payload.lower() for payload in text_payloads))
        finally:
            server.shutdown()

    def test_debug_world_command_allowed_with_entitlement(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            server.entitlement_guard.gates = {
                "operator.world.debug": {"requires": ["operator.world.debug"]},
            }
            session = server.create_session(
                player_id="entitlement_test_player",
                entitlements=["operator.world.debug"],
            )
            self._create_character(server, session.session_id)
            events = server.execute_command(session.session_id, "settime day")
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("time set to" in payload.lower() for payload in text_payloads))
        finally:
            server.shutdown()

    def test_toggle_command_requires_capability_and_entitlement(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            server.entitlement_guard.gates = {
                "operator.feature_profile.toggle": {"requires": ["operator.feature_profile.toggle"]},
            }
            session = server.create_session(player_id="entitlement_test_player")
            self._create_character(server, session.session_id)
            events = server.execute_command(session.session_id, "toggle combat enabled")
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("permission" in payload.lower() for payload in text_payloads))

            session.capabilities.append("authoring.gm")
            events = server.execute_command(session.session_id, "toggle combat enabled")
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("permission" in payload.lower() for payload in text_payloads))

            session.entitlements.append("operator.feature_profile.toggle")
            events = server.execute_command(session.session_id, "toggle combat enabled")
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("set combat mode" in payload.lower() for payload in text_payloads))
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
