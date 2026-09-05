# tests/singles/test_world_effects_heartbeat_full.py
"""Direct coverage for engine/server/world_effects_heartbeat.py's
WorldEffectsHeartbeat: clamping at the upper bound, malformed/out-of-bounds
cell ids in load_cells()/apply_multipliers(), the below-epsilon no-op
branches, and tick()'s decay-to-nothing branch."""

import unittest

from engine.server.world_effects_heartbeat import WorldEffectsHeartbeat


class TestClamp(unittest.TestCase):
    def test_value_above_one_clamps_to_one(self):
        self.assertEqual(1.0, WorldEffectsHeartbeat._clamp(5.0))


class TestLoadCells(unittest.TestCase):
    def setUp(self):
        self.hb = WorldEffectsHeartbeat(width=4, height=4)

    def test_malformed_cell_id_is_skipped(self):
        self.hb.load_cells({"not_a_coordinate": 0.5})
        self.assertEqual({}, self.hb.snapshot())

    def test_non_numeric_coordinate_is_skipped(self):
        self.hb.load_cells({"a,b": 0.5})
        self.assertEqual({}, self.hb.snapshot())

    def test_out_of_bounds_cell_is_skipped(self):
        self.hb.load_cells({"99,99": 0.5, "1,1": 0.7})
        self.assertEqual({"1,1": 0.7}, self.hb.snapshot())


class TestApplyMultipliers(unittest.TestCase):
    def setUp(self):
        self.hb = WorldEffectsHeartbeat(width=4, height=4, change_epsilon=0.1)

    def test_malformed_cell_id_is_skipped(self):
        changed = self.hb.apply_multipliers({"bogus": 2.0})
        self.assertEqual([], changed)

    def test_below_epsilon_change_is_not_recorded(self):
        self.hb.seed_cell(1, 1, 0.5)
        # multiplier of 1.0 leaves the value unchanged -- well under epsilon.
        changed = self.hb.apply_multipliers({"1,1": 1.0})
        self.assertEqual([], changed)

    def test_above_epsilon_change_is_recorded(self):
        self.hb.seed_cell(1, 1, 0.5)
        changed = self.hb.apply_multipliers({"1,1": 0.0})
        self.assertEqual(1, len(changed))
        self.assertEqual("1,1", changed[0].cell_id)
        self.assertEqual(0.0, changed[0].value)


class TestTick(unittest.TestCase):
    def test_decayed_value_below_epsilon_is_dropped(self):
        hb = WorldEffectsHeartbeat(width=4, height=4, decay_factor=1.0, spread_factor=0.0, change_epsilon=0.1)
        hb.seed_cell(1, 1, 0.5)
        hb.tick()
        # decay_factor=1.0 drives retained value to 0.0, well under epsilon,
        # so the cell is dropped from the next generation entirely.
        self.assertEqual({}, hb.snapshot())


if __name__ == "__main__":
    unittest.main()
