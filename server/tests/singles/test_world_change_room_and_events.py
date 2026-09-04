# tests/singles/test_world_change_room_and_events.py
"""Coverage for engine/world/world.py's change_room()/dispatch_event()
branches beyond what test_navigation.py's locked-target-room case covers:
source-room exit_requirements (skill/locked), malformed/unknown
destinations, instance-region quest flagging, and combined dispatch_event
messages."""

from tests.fixtures import GameTestBase
from engine.world.room import Room
from engine.world.region import Region
from engine.items.key import Key


class TestChangeRoomExitRequirements(GameTestBase):
    def _linked_rooms(self):
        region = self.world.get_region("town")
        start = Room("Gate Start", "Before the gate.", {"east": "gate_east"}, obj_id="gate_start")
        end = Room("Gate East", "Beyond the gate.", {"west": "gate_start"}, obj_id="gate_east")
        region.add_room("gate_start", start)
        region.add_room("gate_east", end)
        self.player.current_region_id = "town"
        self.player.current_room_id = "gate_start"
        return start, end

    def test_skill_requirement_failure_blocks_movement(self):
        start, _end = self._linked_rooms()
        start.properties["exit_requirements"] = {
            "east": {"type": "skill", "skill_name": "lockpicking", "difficulty": 9999, "failure_message": "You slip."}
        }
        result = self.world.change_room("east")
        self.assertIn("You slip.", result)
        self.assertEqual("gate_start", self.player.current_room_id)

    def test_skill_requirement_success_allows_movement(self):
        start, _end = self._linked_rooms()
        start.properties["exit_requirements"] = {
            "east": {"type": "skill", "skill_name": "lockpicking", "difficulty": -1000}
        }
        self.world.change_room("east")
        self.assertEqual("gate_east", self.player.current_room_id)

    def test_locked_requirement_without_key_blocks_movement(self):
        start, _end = self._linked_rooms()
        start.properties["exit_requirements"] = {"east": {"type": "locked", "key_id": "key_gate"}}
        result = self.world.change_room("east")
        self.assertIn("locked", result.lower())
        self.assertEqual("gate_start", self.player.current_room_id)

    def test_locked_requirement_with_key_allows_movement(self):
        start, _end = self._linked_rooms()
        start.properties["exit_requirements"] = {"east": {"type": "locked", "key_id": "key_gate"}}
        key = Key(obj_id="key_gate", name="Gate Key", description="Opens the gate.")
        self.player.inventory.add_item(key)
        self.world.change_room("east")
        self.assertEqual("gate_east", self.player.current_room_id)


class TestChangeRoomDestinationResolution(GameTestBase):
    def test_no_exit_in_direction_is_reported(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.world.change_room("nowhere_direction")
        self.assertIn("cannot go", result)

    def test_malformed_destination_with_empty_region_is_reported(self):
        region = self.world.get_region("town")
        room = Room("Weird Exit Room", "Has a malformed exit.", {"east": ":somewhere"}, obj_id="weird_exit_room")
        region.add_room("weird_exit_room", room)
        self.player.current_region_id = "town"
        self.player.current_room_id = "weird_exit_room"
        result = self.world.change_room("east")
        self.assertIn("lost", result.lower())

    def test_destination_targeting_unknown_region_is_reported(self):
        region = self.world.get_region("town")
        room = Room("Portal Room", "Leads nowhere real.", {"east": "not_a_real_region:some_room"}, obj_id="portal_room")
        region.add_room("portal_room", room)
        self.player.current_region_id = "town"
        self.player.current_room_id = "portal_room"
        result = self.world.change_room("east")
        self.assertIn("unknown region", result.lower())

    def test_destination_targeting_unknown_room_is_reported(self):
        region = self.world.get_region("town")
        room = Room("Portal Room 2", "Leads to a missing room.", {"east": "town:not_a_real_room"}, obj_id="portal_room_2")
        region.add_room("portal_room_2", room)
        self.player.current_region_id = "town"
        self.player.current_room_id = "portal_room_2"
        result = self.world.change_room("east")
        self.assertIn("unknown place", result.lower())

    def test_dead_player_cannot_move(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.player.is_alive = False
        result = self.world.change_room("north")
        self.assertIn("cannot move while dead", result)

    def test_no_current_location_reports_lost(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.world.change_room("north")
        self.assertIn("lost in an unknown place", result)


class TestChangeRoomInstanceRegionQuestFlag(GameTestBase):
    def test_entering_matching_instance_region_enables_completion_check(self):
        instance_region = Region("Instance Region", "A temporary instance.", obj_id="instance_test_1")
        room = Room("Instance Room", "Inside the instance.", {}, obj_id="instance_room")
        instance_region.add_room("instance_room", room)
        self.world.add_region("instance_test_1", instance_region)

        town = self.world.get_region("town")
        entry_room = town.get_room("town_square")
        entry_room.exits["portal"] = "instance_test_1:instance_room"

        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1",
            "state": "active",
            "instance_region_id": "instance_test_1",
            "completion_check_enabled": False,
            "stages": [],
        }

        self.world.change_room("portal")
        self.assertTrue(self.player.runtime_state.quests.active["q1"]["completion_check_enabled"])


class TestDispatchEvent(GameTestBase):
    def test_unknown_event_type_returns_none(self):
        self.assertIsNone(self.world.dispatch_event("not_a_real_event", {}))

    def test_npc_killed_with_only_quest_message(self):
        objective = {"type": "kill", "target_template_id": "giant_rat", "required_quantity": 1, "current_quantity": 0}
        self.player.runtime_state.quests.active["q1"] = {
            "instance_id": "q1", "title": "Rats", "giver_instance_id": "quest_board",
            "state": "active", "current_stage_index": 0, "rewards": {},
            "objective": objective,
            "stages": [{"stage_index": 0, "turn_in_id": "quest_board", "objective": objective}],
        }
        from engine.npcs.npc_factory import NPCFactory
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world)
        result = self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
        self.assertIsNotNone(result)


if __name__ == "__main__":
    import unittest
    unittest.main()
