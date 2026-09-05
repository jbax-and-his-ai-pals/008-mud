# tests/singles/test_time_manager_full.py
"""Coverage for engine/core/time_manager.py's TimeManager.update()'s
zero-seconds-per-day and below-threshold branches, get_time_transition_message(),
and apply_loaded_time_state()'s no-saved-state fallback."""

import unittest
from unittest.mock import patch

from engine.core.time_manager import TimeManager


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.tm = TimeManager()

    def test_zero_seconds_per_day_returns_none(self):
        with patch("engine.core.time_manager.TIME_REAL_SECONDS_PER_GAME_DAY", 0):
            self.assertIsNone(self.tm.update(1.0))

    def test_small_dt_below_threshold_skips_recalculation(self):
        before = self.tm.game_time
        result = self.tm.update(0.0000001)
        self.assertIsNone(result)
        self.assertGreater(self.tm.game_time, before)


class TestGetTimeTransitionMessage(unittest.TestCase):
    def setUp(self):
        self.tm = TimeManager()

    def test_known_transitions_return_specific_messages(self):
        self.assertIn("Dawn breaks", self.tm.get_time_transition_message("night", "dawn"))
        self.assertIn("sun climbs higher", self.tm.get_time_transition_message("dawn", "morning"))
        self.assertIn("afternoon sun begins", self.tm.get_time_transition_message("afternoon", "dusk"))
        self.assertIn("Night has fallen", self.tm.get_time_transition_message("dusk", "night"))

    def test_unknown_transition_returns_empty_string(self):
        self.assertEqual("", self.tm.get_time_transition_message("morning", "afternoon"))


class TestApplyLoadedTimeState(unittest.TestCase):
    def setUp(self):
        self.tm = TimeManager()

    def test_none_state_reinitializes_to_default(self):
        self.tm.game_time = 99999.0
        self.tm.apply_loaded_time_state(None)
        self.assertEqual(0.0, self.tm.game_time)

    def test_non_dict_state_reinitializes_to_default(self):
        self.tm.game_time = 99999.0
        self.tm.apply_loaded_time_state("not a dict")
        self.assertEqual(0.0, self.tm.game_time)

    def test_valid_state_restores_game_time(self):
        self.tm.apply_loaded_time_state({"game_time": 5000.0})
        self.assertEqual(5000.0, self.tm.game_time)


if __name__ == "__main__":
    unittest.main()
