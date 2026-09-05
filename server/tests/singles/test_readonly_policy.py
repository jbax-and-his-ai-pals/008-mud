import os
import unittest

from engine.server.headless_server import HeadlessServer
from engine.server.feature_profile import FeatureProfile
from tests.fixtures import FANTASY_FRONTIER


class TestReadonlyPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session = self.server.create_session()
        self.session_id = self.session.session_id
        self.server.execute_command(self.session_id, "char create TestPlayer")
        self.server.feature_profile.world_mutation_mode = "readonly"

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    def test_readonly_blocks_mutating_gameplay_command(self) -> None:
        events = self.server.execute_command(self.session_id, "take potion")
        payloads = self._text_payloads(events)
        self.assertTrue(any("do not have permission" in p.lower() for p in payloads))

    def test_readonly_allows_non_mutating_observation_command(self) -> None:
        events = self.server.execute_command(self.session_id, "look")
        payloads = self._text_payloads(events)
        self.assertFalse(any("do not have permission" in p.lower() for p in payloads))

    def test_readonly_blocks_field_pulse_debug_command(self) -> None:
        events = self.server.execute_command(self.session_id, "field pulse blight 1 1 1.0")
        payloads = self._text_payloads(events)
        self.assertTrue(any("world mutation is disabled by server profile" in p.lower() for p in payloads))


class TestStaticWorldProfile(unittest.TestCase):
    """Regression tests for the static_world.profile.json preset.

    Guards that combat is disabled (not just silently blocked by readonly) and
    that world mutation is readonly, so the profile is semantically consistent.
    """

    _PROFILE_PATH = os.path.join(FANTASY_FRONTIER, "data", "profiles", "static_world.profile.json")

    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, feature_profile=FeatureProfile.load(self._PROFILE_PATH))
        self.session = self.server.create_session()
        self.session_id = self.session.session_id
        # Character creation bypasses the readonly/combat gates (pre-gameplay bootstrapping).
        self.server.execute_command(self.session_id, "char create TestPlayer")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_static_world_combat_mode_is_disabled(self) -> None:
        self.assertEqual("disabled", self.server.feature_profile.combat_mode)

    def test_static_world_mutation_mode_is_readonly(self) -> None:
        self.assertEqual("readonly", self.server.feature_profile.world_mutation_mode)

    def test_static_world_blocks_combat_command(self) -> None:
        events = self.server.execute_command(self.session_id, "attack goblin")
        payloads = [str(e.get("payload", "")) for e in events if e.get("type") == "text"]
        self.assertTrue(
            any("do not have permission" in p.lower() for p in payloads),
            msg="Expected combat command to be blocked in static_world profile.",
        )

    def test_static_world_blocks_take_command(self) -> None:
        events = self.server.execute_command(self.session_id, "take sword")
        payloads = [str(e.get("payload", "")) for e in events if e.get("type") == "text"]
        self.assertTrue(
            any("do not have permission" in p.lower() for p in payloads),
            msg="Expected 'take' to be blocked in readonly static_world profile.",
        )

    def test_static_world_allows_look_command(self) -> None:
        events = self.server.execute_command(self.session_id, "look")
        payloads = [str(e.get("payload", "")) for e in events if e.get("type") == "text"]
        self.assertFalse(
            any("do not have permission" in p.lower() for p in payloads),
            msg="Expected 'look' to be allowed in static_world profile.",
        )


class TestReadonlyArchiveWorldMode(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session = self.server.create_session()
        self.session_id = self.session.session_id
        self.server.execute_command(self.session_id, "char create ArchivePlayer")
        # World mode contract should dominate runtime behavior even if mutation
        # mode was left mutable by operator config drift.
        self.server.feature_profile.world_mode = "readonly_archive"
        self.server.feature_profile.world_mutation_mode = "mutable"

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_readonly_archive_blocks_mutating_command(self) -> None:
        events = self.server.execute_command(self.session_id, "take potion")
        payloads = [str(e.get("payload", "")) for e in events if e.get("type") == "text"]
        self.assertTrue(any("do not have permission" in p.lower() for p in payloads))

    def test_readonly_archive_keeps_runtime_tick_static(self) -> None:
        before = float(self.server.time_manager.game_time)
        tick_events = self.server.tick(self.session_id, dt=120.0)
        after = float(self.server.time_manager.game_time)
        self.assertEqual([], tick_events)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
