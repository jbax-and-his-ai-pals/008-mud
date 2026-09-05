# tests/singles/test_world_update_tick.py
"""Coverage for engine/world/world.py's update() active-region-tracking
loop (a player without a location, a stale region reference, a stale room
reference) and resolve_reference_player()'s explicit player_id lookup."""

from tests.fixtures import GameTestBase
from engine.world.region import Region
from engine.world.room import Room


class TestResolveReferencePlayerById(GameTestBase):
    def test_explicit_player_id_returns_matching_player(self):
        result = self.world.resolve_reference_player(player_id=self.player.obj_id)
        self.assertIs(self.player, result)

    def test_unknown_player_id_falls_back_to_primary_player(self):
        result = self.world.resolve_reference_player(player_id="totally_bogus_player_id_xyz")
        self.assertIs(self.player, result)


class TestWorldUpdateActiveRegionTracking(GameTestBase):
    def setUp(self):
        super().setUp()
        self.world.last_update_time = 0.0

    def test_player_without_location_is_skipped(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        self.world.update()  # must not raise

    def test_stale_region_reference_is_skipped(self):
        self.player.current_region_id = "region_that_does_not_exist_xyz"
        self.player.current_room_id = "some_room"
        self.world.update()  # must not raise

    def test_stale_room_reference_is_skipped(self):
        region = Region("Roomless", "A region missing its rooms.", obj_id="roomless_region")
        self.world.add_region("roomless_region", region)
        self.player.current_region_id = "roomless_region"
        self.player.current_room_id = "room_that_does_not_exist_xyz"
        self.world.update()  # must not raise


if __name__ == "__main__":
    import unittest
    unittest.main()
