import unittest

from engine.server.protocol import (
    PROTOCOL_VERSION,
    build_server_event,
    validate_client_command_envelope,
)


class TestServerProtocol(unittest.TestCase):
    def test_build_server_event_shape(self) -> None:
        event = build_server_event("text", "s1", "hello", 123.45)
        self.assertEqual("text", event["type"])
        self.assertEqual("s1", event["session_id"])
        self.assertEqual("hello", event["payload"])
        self.assertEqual(123.45, event["server_time"])
        self.assertEqual(PROTOCOL_VERSION, event["protocol_version"])

    def test_validate_command_envelope_allows_missing_client_capabilities(self) -> None:
        ok, reason = validate_client_command_envelope(
            {
                "type": "command",
                "session_id": "s1",
                "command_text": "look",
            }
        )
        self.assertTrue(ok, reason)
        self.assertEqual("", reason)

    def test_validate_command_envelope_rejects_non_dict_client_capabilities(self) -> None:
        ok, reason = validate_client_command_envelope(
            {
                "type": "command",
                "session_id": "s1",
                "command_text": "look",
                "client_capabilities": "bad",
            }
        )
        self.assertFalse(ok)
        self.assertIn("client_capabilities", reason)


if __name__ == "__main__":
    unittest.main()
