import unittest

from poc_server import JsonLineMudServer
from tests.fixtures import FANTASY_FRONTIER


class TestAuthoringShellCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.app = JsonLineMudServer(
            "127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER
        )
        self.session = self.app.server.create_session()
        self.session_id = self.session.session_id
        self.app._build_svg_test_payload()

    def tearDown(self) -> None:
        self.app.shutdown()

    def test_translate_dig_acquire(self) -> None:
        envelope, error = self.app._translate_authoring_shell_command(
            self.session_id, "@dig test_glyph_001"
        )
        self.assertIsNone(error)
        self.assertIsNotNone(envelope)
        self.assertEqual("lock_acquire", envelope["type"])
        self.assertEqual("test_glyph_001", envelope["payload"]["asset_id"])

    def test_translate_edit_next(self) -> None:
        envelope, error = self.app._translate_authoring_shell_command(
            self.session_id, "@edit test_glyph_001 next"
        )
        self.assertIsNone(error)
        self.assertIsNotNone(envelope)
        self.assertEqual("asset_update", envelope["type"])
        self.assertEqual("test_glyph_001", envelope["payload"]["asset_id"])
        self.assertEqual(1, envelope["payload"]["base_revision"])
        self.assertIn("<svg", envelope["payload"]["svg"])

    def test_translate_edit_bad_mode(self) -> None:
        envelope, error = self.app._translate_authoring_shell_command(
            self.session_id, "@edit test_glyph_001 now"
        )
        self.assertIsNone(envelope)
        self.assertIn("Unknown @edit mode", error)

    def test_translate_authoring_disabled_by_profile(self) -> None:
        self.app.server.feature_profile.authoring_mode = "disabled"
        envelope, error = self.app._translate_authoring_shell_command(
            self.session_id, "@dig test_glyph_001"
        )
        self.assertIsNone(envelope)
        self.assertIn("disabled by server profile", error)

    def test_apply_dig_and_edit_pipeline(self) -> None:
        dig_envelope, dig_error = self.app._translate_authoring_shell_command(
            self.session_id, "@dig test_glyph_001 acquire"
        )
        self.assertIsNone(dig_error)
        dig_events = self.app._handle_lock_acquire_envelope(self.session_id, dig_envelope)
        self.assertTrue(any(event.get("type") == "lock_acquired" for event in dig_events))

        edit_envelope, edit_error = self.app._translate_authoring_shell_command(
            self.session_id, "@edit test_glyph_001 next"
        )
        self.assertIsNone(edit_error)
        edit_events = self.app._handle_asset_update_envelope(self.session_id, edit_envelope)
        self.assertTrue(any(event.get("type") == "asset_update_accepted" for event in edit_events))
        self.assertTrue(any(event.get("type") == "asset" for event in edit_events))

    def test_mutation_envelope_classifier(self) -> None:
        self.assertTrue(self.app._is_mutation_envelope({"type": "lock_acquire"}))
        self.assertTrue(self.app._is_mutation_envelope({"type": "asset_update"}))
        self.assertTrue(self.app._is_mutation_envelope({"type": "lock_custom"}))
        self.assertTrue(self.app._is_mutation_envelope({"type": "asset_delete"}))
        self.assertFalse(self.app._is_mutation_envelope({"type": "command"}))
        self.assertFalse(self.app._is_mutation_envelope({"type": "disconnect"}))


if __name__ == "__main__":
    unittest.main()
