# tests/singles/test_locked_exit_recovery_hints.py
"""Coverage for World._locked_message and its two call sites in
change_room: a locked exit or door now names the key it needs when one
is authored and resolvable, instead of a bare "is locked" refusal --
but never invents a key for a deliberately pick-only lock (key_id:
null, e.g. fantasy_frontier's jail cell). An authored `failure_message`
still wins over the auto-generated line, mirroring the "skill" exit
type's existing override convention."""

from tests.fixtures import GameTestBase
from engine.world.room import Room


class TestExitRequirementLockedMessage(GameTestBase):
    def setUp(self):
        super().setUp()
        self.region = self.world.get_region("town")
        self.region.add_room("vault", Room("Vault", "A sealed vault.", obj_id="vault"))
        self.room = self.region.get_room("town_square")
        self.room.exits["down"] = "vault"
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

    def test_resolvable_key_is_named(self):
        self.world.item_templates["item_brass_key"] = {"type": "Item", "name": "brass key"}
        self.room.properties["exit_requirements"] = {
            "down": {"type": "locked", "key_id": "item_brass_key"},
        }
        result = self.world.change_room("down")
        self.assertIn("is locked", result)
        self.assertIn("needs a brass key", result)

    def test_unresolvable_key_id_keeps_the_plain_message(self):
        self.room.properties["exit_requirements"] = {
            "down": {"type": "locked", "key_id": None},
        }
        result = self.world.change_room("down")
        self.assertEqual(f"[[RED]]The way down is locked.[[/]]", result)

    def test_authored_failure_message_overrides_the_auto_generated_one(self):
        self.world.item_templates["item_brass_key"] = {"type": "Item", "name": "brass key"}
        self.room.properties["exit_requirements"] = {
            "down": {"type": "locked", "key_id": "item_brass_key", "failure_message": "The vault door won't budge."},
        }
        result = self.world.change_room("down")
        self.assertIn("The vault door won't budge.", result)
        self.assertNotIn("brass key", result)


class TestRoomLevelLockedByMessage(GameTestBase):
    def setUp(self):
        super().setUp()
        self.region = self.world.get_region("town")
        vault = Room("Vault", "A sealed vault.", obj_id="vault2")
        vault.properties["locked_by"] = "item_iron_key"
        self.region.add_room("vault2", vault)
        room = self.region.get_room("town_square")
        room.exits["down"] = "vault2"
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

    def test_resolvable_key_is_named(self):
        self.world.item_templates["item_iron_key"] = {"type": "Item", "name": "iron key"}
        result = self.world.change_room("down")
        self.assertIn("is locked", result)
        self.assertIn("needs an iron key", result)

    def test_unresolvable_key_keeps_the_plain_message(self):
        # No matching item template registered for "item_iron_key".
        result = self.world.change_room("down")
        self.assertIn("The door to Vault is locked.", result)
        self.assertNotIn("needs", result)
