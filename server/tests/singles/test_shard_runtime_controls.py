import unittest
import json
import os
import tempfile

from engine.server.headless_server import HeadlessServer
from engine.server.feature_profile import FeatureProfile
from tests.fixtures import FANTASY_FRONTIER


class TestShardRuntimeControls(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True, tick_rate_hz=10.0)
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_drain_blocks_character_creation(self) -> None:
        ok, _message = self.server.set_shard_runtime_state("drain", "Preparing shutdown")
        self.assertTrue(ok)
        events = self.server.execute_command(self.session.session_id, "char create Tester")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("draining" in text.lower() for text in texts))
        self.assertIsNone(self.server.get_player_for_session(self.session.session_id))

    def test_freeze_blocks_gameplay_commands(self) -> None:
        self.server.execute_command(self.session.session_id, "char create Tester")
        ok, _message = self.server.set_shard_runtime_state("freeze", "Investigating simulation drift")
        self.assertTrue(ok)
        events = self.server.execute_command(self.session.session_id, "look")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("temporarily frozen" in text.lower() for text in texts))

    def test_freeze_disables_tick(self) -> None:
        ok, _message = self.server.set_shard_runtime_state("freeze")
        self.assertTrue(ok)
        self.assertEqual([], self.server.tick(self.session.session_id))

    def test_maintenance_disables_character_creation_and_tick(self) -> None:
        ok, _message = self.server.set_shard_runtime_state("maintenance", "Restarting soon")
        self.assertTrue(ok)
        runtime = self.server.build_shard_runtime_payload()
        self.assertEqual("maintenance", runtime["state"])
        self.assertFalse(runtime["character_creation_enabled"])
        self.assertFalse(runtime["tick_enabled"])
        events = self.server.execute_command(self.session.session_id, "char create Tester")
        texts = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("maintenance" in text.lower() for text in texts))

    def test_initial_runtime_state_is_bootstrap_only_and_can_be_overridden(self) -> None:
        profile_payload = {
            "world": {"mode": "persistent_shard"},
            "persistent_shard": {
                "initial_runtime_state": "maintenance",
                "initial_runtime_message": "Rolling restart",
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(profile_payload, tmp)
            profile_path = tmp.name
        try:
            server = HeadlessServer(
                db_path=":memory:",
                content_set_path=FANTASY_FRONTIER,
                deterministic_test_mode=True,
                tick_rate_hz=10.0,
                feature_profile=FeatureProfile.load(profile_path),
            )
            try:
                self.assertEqual("maintenance", server.shard_runtime_state())
                self.assertEqual("Rolling restart", server.shard_runtime_message())
                ok, _message = server.set_shard_runtime_state("normal")
                self.assertTrue(ok)
                self.assertEqual("normal", server.shard_runtime_state())
                self.assertEqual("", server.shard_runtime_message())
            finally:
                server.shutdown()
        finally:
            os.remove(profile_path)


if __name__ == "__main__":
    unittest.main()
