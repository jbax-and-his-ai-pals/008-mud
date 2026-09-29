# tests/singles/test_player_deadlines.py
"""Downtime does not count: a timer with a minute left has a minute left after a restart.

A player carries a few clock readings that are absolute, not durations: when a sentence
ends, when a spell can be cast again, when a job finishes, when a repeatable quest is
offered again. A restart puts the world on a different clock (a simulated clock starts
over; a wall clock kept running while the server was stopped), so each reading is moved
by the difference between the two clocks when a saved character is handed back.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from engine.player.deadlines import shift_deadlines
from engine.server.headless_server import HeadlessServer
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestShiftDeadlines(GameTestBase):
    def test_every_absolute_reading_moves_and_durations_do_not(self):
        p = self.player
        p.jailed_until = 100.0
        p.runtime_state.magic.cooldowns = {"bolt": 110.0}
        p.runtime_state.work.jobs = [{"work": "chop", "ends_at": 120.0, "started_at": 90.0, "quantity": 3}]
        p.runtime_state.quests.repeatable_available_at = {"daily": 130.0}
        p.active_effects = [{"name": "Burning", "duration_remaining": 7.0}]

        shift_deadlines(p, 50.0)

        self.assertEqual(150.0, p.jailed_until)
        self.assertEqual({"bolt": 160.0}, p.runtime_state.magic.cooldowns)
        self.assertEqual([{"work": "chop", "ends_at": 170.0, "started_at": 140.0, "quantity": 3}], p.runtime_state.work.jobs)
        self.assertEqual({"daily": 180.0}, p.runtime_state.quests.repeatable_available_at)
        self.assertEqual(7.0, p.active_effects[0]["duration_remaining"], "a duration means the same on any clock")

    def test_a_player_who_is_not_jailed_stays_not_jailed(self):
        self.player.jailed_until = None
        shift_deadlines(self.player, 50.0)
        self.assertIsNone(self.player.jailed_until)

    def test_a_shift_of_nothing_changes_nothing(self):
        self.player.jailed_until = 100.0
        shift_deadlines(self.player, 0)
        self.assertEqual(100.0, self.player.jailed_until)


class TestASentenceSurvivesARestart(unittest.TestCase):
    def test_the_time_left_on_a_sentence_is_the_time_left_after_the_restart(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        db = str(Path(scratch) / "state.sqlite3")

        def boot():
            return HeadlessServer(
                db_path=db, content_set_path=str(REPO_ROOT / "content_sets" / "zelda_slice"),
                deterministic_test_mode=True, default_presentation_mode="player",
            )

        first = boot()
        sid = first.create_session(player_id="a").session_id
        first.execute_command(sid, "char create Prisoner")
        hero = first.get_player_for_session(sid)
        for _ in range(400):  # the first clock is well past where a new server's clock starts
            first.tick(sid)
        hero.jailed_until = first.world.clock.now() + 60.0
        first.shutdown()

        second = boot()
        self.addCleanup(second.shutdown)
        sid2 = second.create_session(player_id="b").session_id
        second.execute_command(sid2, "char create Prisoner")
        again = second.get_player_for_session(sid2)
        self.assertAlmostEqual(60.0, again.jailed_until - second.world.clock.now(), delta=1.0)


if __name__ == "__main__":
    unittest.main()
