# tests/singles/test_npc_ai_movement_full.py
"""Coverage for engine/npcs/ai/movement.py's guard clauses and branches
that the existing patrol/schedule/minion-follow tests don't reach:
execute_move's location/region/room/exit guards, perform_wander's chance-
roll/instance-filtering/hostile-safe-zone-avoidance logic, perform_patrol's
guard clauses and wander-fallback, perform_follow's path_override bypass
and target-resolution guards, and perform_schedule's no-game guard,
unchanged-destination skip, and existing-path reuse."""

import time
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room
from engine.world.region import Region
from engine.npcs.ai.movement import execute_move, perform_wander, perform_patrol, perform_follow, perform_schedule


def _npc(world, template="goblin", instance_id="mv_npc"):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id)
    world.add_npc(npc)
    return npc


class TestExecuteMove(GameTestBase):
    def test_no_location_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = None
        npc.current_room_id = None
        self.assertIsNone(execute_move(npc, self.world, self.player, "north"))

    def test_unknown_region_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "not_a_real_region"
        npc.current_room_id = "x"
        self.assertIsNone(execute_move(npc, self.world, self.player, "north"))

    def test_unknown_room_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "not_a_real_room"
        self.assertIsNone(execute_move(npc, self.world, self.player, "north"))

    def test_no_exit_in_direction_returns_none(self):
        npc = _npc(self.world)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        self.assertIsNone(execute_move(npc, self.world, self.player, "nonexistent_direction_xyz"))

    def test_departure_and_arrival_messages_when_player_present(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        region.add_room("mv_start", Room("Start", "x", {"east": "mv_end"}, obj_id="mv_start"))
        region.add_room("mv_end", Room("End", "x", {"west": "mv_start"}, obj_id="mv_end"))
        npc.current_region_id = "town"
        npc.current_room_id = "mv_start"
        self.player.current_region_id = "town"
        self.player.current_room_id = "mv_end"
        result = execute_move(npc, self.world, self.player, "east")
        self.assertEqual("mv_end", npc.current_room_id)
        self.assertIsNotNone(result)


class TestPerformWander(GameTestBase):
    def test_chance_roll_failure_returns_none(self):
        npc = _npc(self.world)
        npc.wander_chance = 0.0
        with patch("engine.npcs.ai.movement.random.random", return_value=0.5):
            self.assertIsNone(perform_wander(npc, self.world, self.player))

    def test_no_location_returns_none(self):
        npc = _npc(self.world)
        npc.wander_chance = 1.0
        npc.current_region_id = None
        npc.current_room_id = None
        self.assertIsNone(perform_wander(npc, self.world, self.player))

    def test_unknown_region_returns_none(self):
        npc = _npc(self.world)
        npc.wander_chance = 1.0
        npc.current_region_id = "not_a_real_region"
        npc.current_room_id = "x"
        self.assertIsNone(perform_wander(npc, self.world, self.player))

    def test_room_with_no_exits_returns_none(self):
        npc = _npc(self.world)
        npc.wander_chance = 1.0
        region = self.world.get_region("town")
        region.add_room("mv_dead_end", Room("Dead End", "x", {}, obj_id="mv_dead_end"))
        npc.current_region_id = "town"
        npc.current_room_id = "mv_dead_end"
        self.assertIsNone(perform_wander(npc, self.world, self.player))

    def test_malformed_exit_with_empty_region_prefix_is_skipped(self):
        # Use a friendly NPC so the hostile safe-zone-avoidance filter
        # (a separate branch) doesn't also exclude the valid "east" exit.
        npc = _npc(self.world, template="village_elder", instance_id="mv_malformed_wanderer")
        npc.wander_chance = 1.0
        region = self.world.get_region("town")
        region.add_room("mv_malformed_exit_room", Room(
            "Room", "x", {"broken": ":nowhere", "east": "town_square"}, obj_id="mv_malformed_exit_room",
        ))
        npc.current_region_id = "town"
        npc.current_room_id = "mv_malformed_exit_room"
        result = perform_wander(npc, self.world, self.player)
        self.assertEqual("town_square", npc.current_room_id)

    def test_avoids_entering_instance_regions_when_not_already_inside_one(self):
        npc = _npc(self.world)
        npc.wander_chance = 1.0
        region = self.world.get_region("town")
        region.add_room("mv_instance_gate", Room(
            "Gate", "x", {"in": "instance_dungeon:entry_room"}, obj_id="mv_instance_gate",
        ))
        npc.current_region_id = "town"
        npc.current_room_id = "mv_instance_gate"
        result = perform_wander(npc, self.world, self.player)
        self.assertIsNone(result)

    def test_npc_inside_instance_only_wanders_within_it(self):
        instance_region = Region("Dungeon Instance", "x", obj_id="instance_dungeon_test")
        instance_region.add_room("in_entry", Room("Entry", "x", {
            "deeper": "in_hall", "out": "town:town_square",
        }, obj_id="in_entry"))
        instance_region.add_room("in_hall", Room("Hall", "x", {}, obj_id="in_hall"))
        self.world.add_region("instance_dungeon_test", instance_region)

        npc = _npc(self.world)
        npc.wander_chance = 1.0
        npc.current_region_id = "instance_dungeon_test"
        npc.current_room_id = "in_entry"
        with patch("engine.npcs.ai.movement.random.choice", side_effect=lambda opts: opts[0]):
            perform_wander(npc, self.world, self.player)
        self.assertEqual("instance_dungeon_test", npc.current_region_id)
        self.assertEqual("in_hall", npc.current_room_id)

    def test_hostile_npc_avoids_safe_zone_exits_when_unsafe_alternative_exists(self):
        region = self.world.get_region("town")
        region.properties["safe_zone"] = True
        danger_region = Region("Danger Zone", "x", obj_id="mv_danger_zone")
        danger_region.properties["safe_zone"] = False
        danger_region.add_room("mv_danger_room", Room("Danger", "x", {}, obj_id="mv_danger_room"))
        self.world.add_region("mv_danger_zone", danger_region)

        region.add_room("mv_hostile_start", Room(
            "Start", "x", {"south": "town_square", "north": "mv_danger_zone:mv_danger_room"},
            obj_id="mv_hostile_start",
        ))
        npc = _npc(self.world)
        npc.wander_chance = 1.0
        npc.faction = "hostile"
        npc.current_region_id = "town"
        npc.current_room_id = "mv_hostile_start"
        with patch("engine.npcs.ai.movement.random.choice", side_effect=lambda opts: opts[0]):
            perform_wander(npc, self.world, self.player)
        self.assertEqual("mv_danger_zone", npc.current_region_id)

    def test_friendly_npc_may_wander_into_safe_zones(self):
        region = self.world.get_region("town")
        region.add_room("mv_friendly_start", Room("Start", "x", {"east": "town_square"}, obj_id="mv_friendly_start"))
        npc = _npc(self.world, template="village_elder", instance_id="mv_friendly_wanderer")
        npc.wander_chance = 1.0
        npc.faction = "friendly"
        npc.current_region_id = "town"
        npc.current_room_id = "mv_friendly_start"
        perform_wander(npc, self.world, self.player)
        self.assertEqual("town_square", npc.current_room_id)


class TestPerformPatrol(GameTestBase):
    def test_no_patrol_points_returns_none(self):
        npc = _npc(self.world)
        npc.patrol_points = []
        self.assertIsNone(perform_patrol(npc, self.world, self.player))

    def test_missing_location_or_home_region_returns_none(self):
        npc = _npc(self.world)
        npc.patrol_points = ["some_room"]
        npc.patrol_index = 0
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.home_region_id = None
        self.assertIsNone(perform_patrol(npc, self.world, self.player))

    def test_no_path_falls_back_to_wander(self):
        npc = _npc(self.world)
        npc.patrol_points = ["unreachable_room_xyz"]
        npc.patrol_index = 0
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.home_region_id = "town"
        npc.wander_chance = 1.0
        with patch.object(self.world, "find_path", return_value=None), \
             patch("engine.npcs.ai.movement.perform_wander", return_value="wandered") as mock_wander:
            result = perform_patrol(npc, self.world, self.player)
        mock_wander.assert_called_once()
        self.assertEqual("wandered", result)


class TestPerformFollow(GameTestBase):
    def test_path_override_bypasses_target_resolution(self):
        npc = _npc(self.world)
        region = self.world.get_region("town")
        region.add_room("mv_follow_start", Room("Start", "x", {"east": "town_square"}, obj_id="mv_follow_start"))
        npc.current_region_id = "town"
        npc.current_room_id = "mv_follow_start"
        result = perform_follow(npc, self.world, self.player, path_override=["east"])
        self.assertEqual("town_square", npc.current_room_id)

    def test_no_follow_target_returns_none(self):
        npc = _npc(self.world)
        npc.follow_target = None
        self.assertIsNone(perform_follow(npc, self.world, self.player))

    def test_missing_or_dead_target_clears_follow_target(self):
        npc = _npc(self.world)
        npc.follow_target = "not_a_real_target_id"
        result = perform_follow(npc, self.world, self.player)
        self.assertIsNone(result)
        self.assertIsNone(npc.follow_target)

    def test_dead_follow_target_clears_follow_target(self):
        target = _npc(self.world, instance_id="mv_dead_follow_target")
        target.is_alive = False
        npc = _npc(self.world, instance_id="mv_follower_of_dead")
        npc.follow_target = target.obj_id
        result = perform_follow(npc, self.world, self.player)
        self.assertIsNone(result)
        self.assertIsNone(npc.follow_target)

    def test_same_room_as_target_does_not_move(self):
        target = _npc(self.world, instance_id="mv_same_room_target")
        npc = _npc(self.world, instance_id="mv_same_room_follower")
        for n in (target, npc):
            n.current_region_id = "town"
            n.current_room_id = "town_square"
        npc.follow_target = target.obj_id
        self.assertIsNone(perform_follow(npc, self.world, self.player))

    def test_missing_locations_returns_none(self):
        target = _npc(self.world, instance_id="mv_no_loc_target")
        target.current_region_id = None
        target.current_room_id = None
        npc = _npc(self.world, instance_id="mv_no_loc_follower")
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.follow_target = target.obj_id
        self.assertIsNone(perform_follow(npc, self.world, self.player))

    def test_no_path_to_target_returns_none(self):
        target = _npc(self.world, instance_id="mv_unreachable_target")
        target.current_region_id = "town"
        target.current_room_id = "town_square"
        npc = _npc(self.world, instance_id="mv_unreachable_follower")
        npc.current_region_id = "town"
        npc.current_room_id = "market_square"
        npc.follow_target = target.obj_id
        with patch.object(self.world, "find_path", return_value=None):
            self.assertIsNone(perform_follow(npc, self.world, self.player))


class TestPerformSchedule(GameTestBase):
    def _schedule_npc(self):
        region = Region("Schedule Region", "x", obj_id="mv_sched_region")
        home = Room("Home", "x", {"north": "hallway"}, obj_id="home")
        hallway = Room("Hallway", "x", {"south": "home", "north": "work"}, obj_id="hallway")
        work = Room("Work", "x", {"south": "hallway"}, obj_id="work")
        region.add_room("home", home)
        region.add_room("hallway", hallway)
        region.add_room("work", work)
        self.world.add_region("mv_sched_region", region)
        npc = _npc(self.world, instance_id="mv_sched_npc")
        npc.current_region_id = "mv_sched_region"
        npc.current_room_id = "home"
        return npc

    def test_no_game_returns_none(self):
        npc = self._schedule_npc()
        with patch.object(self.world, "game", None):
            self.assertIsNone(perform_schedule(npc, self.world, self.player))

    def test_empty_schedule_returns_none(self):
        npc = self._schedule_npc()
        npc.schedule = {}
        self.assertIsNone(perform_schedule(npc, self.world, self.player))

    def test_wraps_around_to_latest_entry_when_current_hour_before_all(self):
        npc = self._schedule_npc()
        npc.schedule = {"20": {"region_id": "mv_sched_region", "room_id": "work", "activity": "late_shift"}}
        self.game.time_manager.hour = 3
        perform_schedule(npc, self.world, self.player)
        self.assertEqual("late_shift", npc.ai_state.get("current_activity"))

    def test_already_at_destination_does_nothing(self):
        npc = self._schedule_npc()
        npc.schedule = {"8": {"region_id": "mv_sched_region", "room_id": "home", "activity": "sleeping"}}
        self.game.time_manager.hour = 8
        result = perform_schedule(npc, self.world, self.player)
        self.assertIsNone(result)
        self.assertEqual([], npc.current_path)

    def test_unchanged_destination_does_not_reset_path(self):
        npc = self._schedule_npc()
        npc.schedule = {"8": {"region_id": "mv_sched_region", "room_id": "work", "activity": "working"}}
        self.game.time_manager.hour = 8
        perform_schedule(npc, self.world, self.player)  # establishes destination + path
        npc.current_path = ["north", "extra_marker"]
        perform_schedule(npc, self.world, self.player)  # same destination again
        self.assertIn("extra_marker", npc.current_path)

    def test_missing_location_during_pathfind_returns_none(self):
        npc = self._schedule_npc()
        npc.current_region_id = None
        npc.current_room_id = None
        npc.schedule = {"8": {"region_id": "mv_sched_region", "room_id": "work", "activity": "working"}}
        self.game.time_manager.hour = 8
        self.assertIsNone(perform_schedule(npc, self.world, self.player))

    def test_no_path_found_clears_destination(self):
        npc = self._schedule_npc()
        npc.schedule = {"8": {"region_id": "mv_sched_region", "room_id": "work", "activity": "working"}}
        self.game.time_manager.hour = 8
        with patch.object(self.world, "find_path", return_value=None):
            result = perform_schedule(npc, self.world, self.player)
        self.assertIsNone(result)
        self.assertIsNone(npc.schedule_destination)

    def test_moves_along_existing_path(self):
        npc = self._schedule_npc()
        npc.schedule = {"8": {"region_id": "mv_sched_region", "room_id": "work", "activity": "working"}}
        self.game.time_manager.hour = 8
        perform_schedule(npc, self.world, self.player)
        self.assertEqual("hallway", npc.current_room_id)


if __name__ == "__main__":
    import unittest
    unittest.main()
