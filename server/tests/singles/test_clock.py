# tests/singles/test_clock.py
"""Coverage for engine/core/clock.py's WallClock and SimulatedClock."""

import time
import unittest

from engine.core.clock import SimulatedClock, WallClock


class TestWallClock(unittest.TestCase):
    def test_now_tracks_real_time(self):
        clock = WallClock()
        before = time.time()
        now = clock.now()
        after = time.time()
        self.assertLessEqual(before, now)
        self.assertLessEqual(now, after)

    def test_advance_is_a_no_op(self):
        clock = WallClock()
        first = clock.now()
        clock.advance(1000.0)
        second = clock.now()
        # Real time marches on regardless of advance(); it should not have
        # jumped forward by anywhere near the requested amount.
        self.assertLess(second - first, 1.0)


class TestSimulatedClock(unittest.TestCase):
    def test_defaults_to_a_positive_epoch(self):
        self.assertGreater(SimulatedClock().now(), 0.0)

    def test_advance_accumulates(self):
        clock = SimulatedClock(start=10.0)
        clock.advance(5.0)
        self.assertEqual(15.0, clock.now())
        clock.advance(2.5)
        self.assertEqual(17.5, clock.now())

    def test_set_overrides_the_current_value(self):
        clock = SimulatedClock(start=10.0)
        clock.set(500.0)
        self.assertEqual(500.0, clock.now())

    def test_time_never_advances_on_its_own(self):
        clock = SimulatedClock(start=1.0)
        value_a = clock.now()
        time.sleep(0.01)
        value_b = clock.now()
        self.assertEqual(value_a, value_b)


if __name__ == "__main__":
    unittest.main()
