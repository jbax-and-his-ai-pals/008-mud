# tests/singles/test_arrival_characterisation.py
"""What happens when a player arrives somewhere, pinned before it moved.

`World.change_room` did two jobs in one body: decide whether the way is open (skill
roll, key) and then *arrive* (mark the room visited, set the location, tell the quest
manager, flag an instance quest, print the region banner, look, add the travel note, pay
first-arrival notes, append quest updates). Exit conditions, teleport and triggers all
need the second half without the first, so it is now `_arrive` and the first is
`_evaluate_exit_gate`. These tests describe the behaviour both halves must keep.
"""

from unittest import mock

from tests.fixtures import GameTestBase


class TestArrival(GameTestBase):
    def _step(self):
        """(direction, region, room) of an exit from where the player stands, in the same region."""
        room = self.world.get_current_room(self.player)
        for direction, destination in sorted(room.exits.items()):
            if ":" not in destination and self.world.get_region(self.player.current_region_id).get_room(destination):
                return direction, self.player.current_region_id, destination
        self.fail("no same-region exit to walk")

    def _cross_region(self):
        for region_id, region in self.world.regions.items():
            for room_id, room in region.rooms.items():
                for direction, destination in room.exits.items():
                    if ":" in destination and destination.split(":")[0] != region_id:
                        return region_id, room_id, direction, destination
        self.fail("no cross-region exit")

    def test_walking_sets_the_location_and_marks_the_room_visited(self):
        direction, region, room = self._step()
        self.world.get_region(region).get_room(room).visited = False
        self.world.change_room(direction, self.player)
        self.assertEqual((region, room), (self.player.current_region_id, self.player.current_room_id))
        self.assertTrue(self.world.get_region(region).get_room(room).visited)

    def test_a_refused_move_leaves_the_player_and_the_room_alone(self):
        direction, region, room = self._step()
        origin = (self.player.current_region_id, self.player.current_room_id)
        target = self.world.get_region(region).get_room(room)
        target.visited = False
        here = self.world.get_current_room(self.player)
        here.properties["exit_requirements"] = {direction: {"type": "locked", "key_id": "item_nobody_has"}}
        text = self.world.change_room(direction, self.player)
        self.assertEqual(origin, (self.player.current_region_id, self.player.current_room_id))
        self.assertFalse(target.visited)
        self.assertIn("locked", text)

    def test_the_output_is_the_room_description(self):
        direction, region, room = self._step()
        text = self.world.change_room(direction, self.player)
        self.assertIn(self.world.get_region(region).get_room(room).name.upper(), text)

    def test_a_new_region_is_announced_and_a_same_region_move_is_not(self):
        direction, _region, _room = self._step()
        self.assertNotIn("You have entered", self.world.change_room(direction, self.player))
        origin_region, origin_room, cross, _dest = self._cross_region()
        self.player.current_region_id, self.player.current_room_id = origin_region, origin_room
        text = self.world.change_room(cross, self.player)
        self.assertIn("You have entered", text)
        self.assertTrue(text.index("You have entered") < text.index(self.world.get_current_room(self.player).name.upper()))

    def test_the_quest_manager_is_told_after_the_location_is_set(self):
        direction, region, room = self._step()
        seen = []
        original = self.world.quest_manager.handle_room_entry

        def spy(player):
            seen.append((player.current_region_id, player.current_room_id))
            return ["[Quest] something happened."]

        with mock.patch.object(self.world.quest_manager, "handle_room_entry", side_effect=spy):
            text = self.world.change_room(direction, self.player)
        self.assertEqual([(region, room)], seen)
        self.assertTrue(text.rstrip().endswith("[Quest] something happened."), "quest updates come last")
        self.assertIsNotNone(original)

    def test_a_travel_note_follows_the_room_and_precedes_the_quest_updates(self):
        direction, region, room = self._step()
        manager = getattr(self.world.game, "weather_manager", None)
        self.assertIsNotNone(manager)
        with mock.patch.object(manager, "travel_note", return_value="A cold wind pushes at your back."), \
                mock.patch.object(self.world.quest_manager, "handle_room_entry", return_value=["[Quest] done."]):
            text = self.world.change_room(direction, self.player)
        self.assertLess(text.index(self.world.get_region(region).get_room(room).name.upper()), text.index("cold wind"))
        self.assertLess(text.index("cold wind"), text.index("[Quest] done."))
