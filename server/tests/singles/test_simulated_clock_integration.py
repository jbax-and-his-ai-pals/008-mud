# tests/singles/test_simulated_clock_integration.py
"""Proves gameplay timers (combat cooldown, jail sentence) advance purely
from HeadlessServer's SimulatedClock under deterministic_test_mode, with no
dependency on real elapsed wall-clock time. This is the behavior
`engine/core/clock.py` exists for: a fast headless journey should be able to
clear a real cooldown or serve out a jail sentence without sleeping."""

import time
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestSimulatedClockDrivesCombatCooldown(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.server.tick_dt = 5.0  # comfortably above any attack cooldown
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(str(e.get("payload", "")) for e in events if e.get("type") == "text")

    def test_repeated_attacks_are_never_cooldown_blocked(self):
        wall_clock_start = time.time()
        self._text("char create ClockTester")
        self._text("spawn goblin")
        first_attack = self._text("attack goblin")
        second_attack = self._text("attack goblin")
        wall_clock_elapsed = time.time() - wall_clock_start

        self.assertNotIn("Not ready", first_attack)
        self.assertNotIn("Not ready", second_attack)
        # Two attacks each gated by a real cooldown "cleared" purely by the
        # simulated clock advancing tick_dt per command -- proof this ran
        # without sleeping for the cooldown to pass in real time.
        self.assertLess(wall_clock_elapsed, 5.0)


class TestSimulatedClockDrivesJailRelease(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        self.server.tick_dt = 5.0
        self.session = self.server.create_session()

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(str(e.get("payload", "")) for e in events if e.get("type") == "text")

    def test_sentence_elapses_and_releases_via_the_simulated_clock_alone(self):
        self._text("char create ClockTester")
        player = self.server.get_player_for_session(self.session.session_id)

        wall_clock_start = time.time()
        self.server.world.crime_manager.send_to_jail(player, sentence_seconds=12.0)
        self.assertIsNotNone(player.jailed_until)

        released_text = ""
        for _ in range(10):
            released_text = self._text("wait")
            if "sentence is served" in released_text:
                break
        wall_clock_elapsed = time.time() - wall_clock_start

        self.assertIn("sentence is served", released_text)
        self.assertIsNone(player.jailed_until)
        # 12 simulated seconds of sentence, served purely by tick_dt=5.0
        # advancing the SimulatedClock across a few `wait` commands -- no
        # real sleeping involved.
        self.assertLess(wall_clock_elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
