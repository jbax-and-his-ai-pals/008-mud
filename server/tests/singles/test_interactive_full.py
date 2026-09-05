# tests/singles/test_interactive_full.py
"""Coverage for engine/items/interactive.py: the stackable kwarg being
stripped, a linked_action that isn't a "toggle_exit:" prefix, target_id
resolution via the current region (no "region:room" prefix), a missing
target room, and both the "on" (hidden exit not found) and "off"
(exit not present/not hidden) toggle-exit no-op branches."""

import unittest

from tests.fixtures import GameTestBase
from engine.items.interactive import Interactive
from engine.world.region import Region
from engine.world.room import Room


class TestInteractiveInit(unittest.TestCase):
    def test_stackable_kwarg_is_stripped(self):
        lever = Interactive(name="Lever", stackable=True)
        self.assertFalse(lever.stackable)


class TestInteractiveInteract(GameTestBase):
    def setUp(self):
        super().setUp()
        self.region = Region("Interactive Region", "Testing.", obj_id="interactive_region")
        self.room = Room("Lever Room", "Has a lever.", obj_id="interactive_room")
        self.region.add_room("interactive_room", self.room)
        self.world.add_region("interactive_region", self.region)

    def test_non_toggle_exit_linked_action_is_a_noop(self):
        lever = Interactive(
            name="Switch", linked_target_id="interactive_region:interactive_room",
            linked_action="some_other_action",
        )
        result = lever.interact(self.player, self.world)
        self.assertIn("State:", result)

    def test_target_resolved_via_current_region_without_prefix(self):
        self.player.current_region_id = "interactive_region"
        self.player.current_room_id = "interactive_room"
        self.room.properties["hidden_exits"] = {"north": "some_other_room"}
        lever = Interactive(
            name="Switch", linked_target_id="interactive_room",  # no "region:" prefix
            linked_action="toggle_exit:north",
        )
        result = lever.interact(self.player, self.world)
        self.assertIn("grinding sound", result)
        self.assertEqual(self.room.exits.get("north"), "some_other_room")

    def test_missing_target_room_is_a_noop(self):
        lever = Interactive(
            name="Switch", linked_target_id="interactive_region:totally_bogus_room_xyz",
            linked_action="toggle_exit:north",
        )
        result = lever.interact(self.player, self.world)
        self.assertIn("State:", result)
        self.assertNotIn("grinding", result)

    def test_turning_on_without_a_hidden_exit_is_a_noop(self):
        lever = Interactive(
            name="Switch", state="off",
            linked_target_id="interactive_region:interactive_room",
            linked_action="toggle_exit:north",
        )
        # No hidden_exits configured at all.
        result = lever.interact(self.player, self.world)
        self.assertIn("State:", result)
        self.assertNotIn("grinding", result)
        self.assertNotIn("north", self.room.exits)

    def test_turning_off_an_exit_not_present_is_a_noop(self):
        self.room.properties["hidden_exits"] = {"north": "some_other_room"}
        lever = Interactive(
            name="Switch", state="on",  # will toggle to "off"
            linked_target_id="interactive_region:interactive_room",
            linked_action="toggle_exit:north",
        )
        # "north" was never actually opened in room.exits.
        result = lever.interact(self.player, self.world)
        self.assertIn("State:", result)
        self.assertNotIn("seals shut", result)


if __name__ == "__main__":
    unittest.main()
