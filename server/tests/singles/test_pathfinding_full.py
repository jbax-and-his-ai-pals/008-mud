# tests/singles/test_pathfinding_full.py
"""Coverage for engine/utils/pathfinding.py's find_path: the
same-start-and-goal shortcut, a stale region reference mid-search, a
stale room reference mid-search, and an exit pointing at a
nonexistent destination room."""

import unittest

from tests.fixtures import GameTestBase
from engine.utils.pathfinding import find_path
from engine.world.region import Region
from engine.world.room import Room


class TestFindPath(GameTestBase):
    def test_same_start_and_goal_returns_empty_path(self):
        result = find_path(self.world, "town", "town_square", "town", "town_square")
        self.assertEqual(result, [])

    def test_nonexistent_source_region_is_skipped(self):
        # The start node is pushed onto the queue without any prior
        # validation, so an invalid source region surfaces only once it's
        # popped and looked up -- exercising the "region not found" branch.
        result = find_path(self.world, "totally_bogus_source_region_xyz", "some_room", "town", "town_square")
        self.assertIsNone(result)

    def test_nonexistent_source_room_is_skipped(self):
        # Same idea, but with a valid region and an invalid room within it.
        result = find_path(self.world, "town", "totally_bogus_source_room_xyz", "town", "town_square")
        self.assertIsNone(result)

    def test_exit_pointing_to_nonexistent_destination_room_is_skipped(self):
        region = Region("Broken Exit Region", "Testing", obj_id="pf_broken_exit_region")
        room_a = Room("Room A", "Start", {"east": "pf_room_that_does_not_exist"}, obj_id="pf_room_a3")
        room_b = Room("Room B", "Real destination", obj_id="pf_room_b3")
        region.add_room("pf_room_a3", room_a)
        region.add_room("pf_room_b3", room_b)
        self.world.add_region("pf_broken_exit_region", region)
        result = find_path(
            self.world, "pf_broken_exit_region", "pf_room_a3",
            "pf_broken_exit_region", "pf_room_b3",
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
