import os
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from tests.singles.snapshot_assertions import assert_snapshot

FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestHeadlessServerDeterministicSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
            tick_rate_hz=10.0,
        )
        self.session = self.server.create_session(player_id="regression_player")

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_baseline_command_sequence_snapshot(self) -> None:
        commands = ["look", "status", "inventory", "nearby", "north", "look"]
        events = []
        for command_text in commands:
            events.extend(self.server.execute_command(self.session.session_id, command_text))

        snapshot_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "snapshots", "headless_server_baseline_events.json")
        )
        assert_snapshot(self, snapshot_path, {"commands": commands, "events": events})


if __name__ == "__main__":
    unittest.main()
