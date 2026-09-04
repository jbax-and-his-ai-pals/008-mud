# tests/singles/test_protocol.py
"""Coverage for engine/server/protocol.py's build_server_event() and
validate_client_command_envelope()'s full field-validation matrix."""

import unittest

from engine.server.protocol import (
    build_server_event, validate_client_command_envelope, PROTOCOL_VERSION,
)


class TestBuildServerEvent(unittest.TestCase):
    def test_builds_expected_shape(self):
        event = build_server_event("text", "sess1", {"msg": "hi"}, 123.45)
        self.assertEqual({
            "type": "text", "session_id": "sess1", "payload": {"msg": "hi"},
            "server_time": 123.45, "protocol_version": PROTOCOL_VERSION,
        }, event)


class TestValidateClientCommandEnvelope(unittest.TestCase):
    def _valid(self, **overrides):
        env = {"type": "command", "session_id": "sess1", "command_text": "look"}
        env.update(overrides)
        return env

    def test_valid_envelope_passes(self):
        ok, msg = validate_client_command_envelope(self._valid())
        self.assertTrue(ok)
        self.assertEqual("", msg)

    def test_missing_fields_are_reported(self):
        ok, msg = validate_client_command_envelope({"type": "command"})
        self.assertFalse(ok)
        self.assertIn("Missing fields", msg)
        self.assertIn("command_text", msg)
        self.assertIn("session_id", msg)

    def test_wrong_type_is_rejected(self):
        ok, msg = validate_client_command_envelope(self._valid(type="not_command"))
        self.assertFalse(ok)
        self.assertIn("must be 'command'", msg)

    def test_blank_session_id_is_rejected(self):
        ok, msg = validate_client_command_envelope(self._valid(session_id=""))
        self.assertFalse(ok)
        self.assertIn("session_id must be", msg)

    def test_non_string_session_id_is_rejected(self):
        ok, msg = validate_client_command_envelope(self._valid(session_id=123))
        self.assertFalse(ok)
        self.assertIn("session_id must be", msg)

    def test_non_string_command_text_is_rejected(self):
        ok, msg = validate_client_command_envelope(self._valid(command_text=123))
        self.assertFalse(ok)
        self.assertIn("command_text must be a string", msg)

    def test_non_dict_client_capabilities_is_rejected(self):
        ok, msg = validate_client_command_envelope(self._valid(client_capabilities="not_a_dict"))
        self.assertFalse(ok)
        self.assertIn("client_capabilities must be an object", msg)

    def test_dict_client_capabilities_is_accepted(self):
        ok, msg = validate_client_command_envelope(self._valid(client_capabilities={"foo": True}))
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
