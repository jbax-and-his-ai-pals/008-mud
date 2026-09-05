# tests/singles/test_world_pick_lock_direction.py
"""Coverage for engine/world/world.py's attempt_pick_lock_direction(), which
handles two cases: a source-room exit_requirements lock (partially covered
by test_command_room_context.py) and a destination-room locked_by lock
(previously entirely untested).

Note: both of this method's `if not active_player: return "Player not
found."` guards are left untested as unreachable -- `current_room` (and,
for the destination-lock case, `room`) can only be truthy here because
get_current_room()/get_region() already re-resolved the exact same
active_player via resolve_reference_player() and found a home for them;
if active_player were falsy that resolution would have failed too, and
the method already returns earlier ("You are nowhere.") in that case."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.room import Room
from engine.items.lockpick import Lockpick


class TestSourceExitRequirementLock(GameTestBase):
    def _linked_rooms_with_lock(self, pick_difficulty=10):
        region = self.world.get_region("town")
        start = Room("Pick Start", "Before the lock.", {"east": "pick_east"}, obj_id="pick_start")
        end = Room("Pick East", "Beyond the lock.", {"west": "pick_start"}, obj_id="pick_east")
        start.properties["exit_requirements"] = {
            "east": {"type": "locked", "key_id": "missing_key", "pick_difficulty": pick_difficulty}
        }
        region.add_room("pick_start", start)
        region.add_room("pick_east", end)
        self.player.current_region_id = "town"
        self.player.current_room_id = "pick_start"
        return start

    def test_no_current_room_reports_nowhere(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        self.assertEqual("You are nowhere.", self.world.attempt_pick_lock_direction("east"))

    def test_difficulty_over_100_cannot_be_picked(self):
        self._linked_rooms_with_lock(pick_difficulty=101)
        result = self.world.attempt_pick_lock_direction("east")
        self.assertEqual("This lock cannot be picked.", result)

    def test_no_lockpick_is_reported(self):
        self._linked_rooms_with_lock()
        result = self.world.attempt_pick_lock_direction("east")
        self.assertEqual("You need a lockpick.", result)

    @patch("engine.world.world.SkillSystem.attempt_check")
    def test_successful_pick_removes_requirement(self, mock_check):
        mock_check.return_value = (True, "")
        start = self._linked_rooms_with_lock()
        self.player.inventory.add_item(Lockpick(obj_id="lockpick1", name="Lockpick", description="A pick."))
        result = self.world.attempt_pick_lock_direction("east")
        self.assertIn("unlock the way east", result)
        self.assertNotIn("east", start.properties.get("exit_requirements", {}))

    @patch("engine.world.world.SkillSystem.attempt_check")
    def test_failed_pick_keeps_requirement(self, mock_check):
        mock_check.return_value = (False, "")
        start = self._linked_rooms_with_lock()
        self.player.inventory.add_item(Lockpick(obj_id="lockpick1", name="Lockpick", description="A pick."))
        result = self.world.attempt_pick_lock_direction("east")
        self.assertIn("fail to pick the lock", result)
        self.assertIn("east", start.properties.get("exit_requirements", {}))


class TestDestinationLockedByLock(GameTestBase):
    def _linked_rooms_with_target_lock(self):
        region = self.world.get_region("town")
        start = Room("Vault Start", "Before the vault.", {"east": "vault_east"}, obj_id="vault_start")
        end = Room("Vault East", "The vault.", {"west": "vault_start"}, obj_id="vault_east")
        end.update_property("locked_by", "vault_key")
        region.add_room("vault_start", start)
        region.add_room("vault_east", end)
        self.player.current_region_id = "town"
        self.player.current_room_id = "vault_start"
        return end

    def test_no_lockpick_is_reported(self):
        self._linked_rooms_with_target_lock()
        result = self.world.attempt_pick_lock_direction("east")
        self.assertEqual("You need a lockpick.", result)

    @patch("engine.world.world.SkillSystem.attempt_check")
    def test_successful_pick_unlocks_destination_room(self, mock_check):
        mock_check.return_value = (True, "")
        end = self._linked_rooms_with_target_lock()
        self.player.inventory.add_item(Lockpick(obj_id="lockpick1", name="Lockpick", description="A pick."))
        result = self.world.attempt_pick_lock_direction("east")
        self.assertIn("unlock the door", result)
        self.assertIsNone(end.properties.get("locked_by"))

    @patch("engine.world.world.SkillSystem.attempt_check")
    def test_failed_pick_keeps_destination_locked(self, mock_check):
        mock_check.return_value = (False, "")
        end = self._linked_rooms_with_target_lock()
        self.player.inventory.add_item(Lockpick(obj_id="lockpick1", name="Lockpick", description="A pick."))
        result = self.world.attempt_pick_lock_direction("east")
        self.assertIn("fail to pick the lock", result)
        self.assertEqual("vault_key", end.properties.get("locked_by"))

    def test_no_exit_in_direction_reports_nothing_locked(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.world.attempt_pick_lock_direction("nowhere_direction")
        self.assertEqual("There is nothing locked in that direction.", result)

    def test_destination_in_unknown_region_reports_nothing_locked(self):
        region = self.world.get_region("town")
        start = Room("Portal Start", "A portal to nowhere.", {"east": "nonexistent_region:some_room"}, obj_id="portal_start")
        region.add_room("portal_start", start)
        self.player.current_region_id = "town"
        self.player.current_room_id = "portal_start"
        result = self.world.attempt_pick_lock_direction("east")
        self.assertEqual("There is nothing locked in that direction.", result)

    def test_unlocked_destination_reports_nothing_locked(self):
        region = self.world.get_region("town")
        start = Room("Open Start", "Before an open room.", {"east": "open_east"}, obj_id="open_start")
        end = Room("Open East", "Nothing locked here.", {"west": "open_start"}, obj_id="open_east")
        region.add_room("open_start", start)
        region.add_room("open_east", end)
        self.player.current_region_id = "town"
        self.player.current_room_id = "open_start"
        result = self.world.attempt_pick_lock_direction("east")
        self.assertEqual("There is nothing locked in that direction.", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
