import unittest

from engine.commands.command_system import command, unregister_command
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestEntitlementAuthorization(unittest.TestCase):
    _TEST_COMMAND_NAME = "entitlementprobe"

    @classmethod
    def setUpClass(cls) -> None:
        @command(
            cls._TEST_COMMAND_NAME,
            help_text="entitlement probe",
            entitlements=["operator.entitlementprobe.use"],
        )
        def _entitlement_probe(_args, _ctx) -> str:
            return "probe command executed"

    @classmethod
    def tearDownClass(cls) -> None:
        unregister_command(cls._TEST_COMMAND_NAME)

    def test_command_denied_without_entitlement(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=FANTASY_FRONTIER, require_character_creation=False
        )
        try:
            server.entitlement_guard.gates = {
                "operator.entitlementprobe.use": {"requires": ["operator.entitlementprobe.use"]},
            }
            session = server.create_session(player_id="entitlement_test_player")
            server.execute_command(session.session_id, "char create EntitlementTester")
            events = server.execute_command(session.session_id, self._TEST_COMMAND_NAME)
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("permission" in payload.lower() for payload in text_payloads))
        finally:
            server.shutdown()

    def test_command_allowed_with_entitlement(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=FANTASY_FRONTIER, require_character_creation=False
        )
        try:
            server.entitlement_guard.gates = {
                "operator.entitlementprobe.use": {"requires": ["operator.entitlementprobe.use"]},
            }
            session = server.create_session(
                player_id="entitlement_test_player",
                entitlements=["operator.entitlementprobe.use"],
            )
            server.execute_command(session.session_id, "char create EntitlementTester")
            events = server.execute_command(session.session_id, self._TEST_COMMAND_NAME)
            text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
            self.assertTrue(any("probe command executed" in payload.lower() for payload in text_payloads))
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
