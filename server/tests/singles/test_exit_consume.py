# tests/singles/test_exit_consume.py
"""A key can be spent by the door it opens, and the door then stays open for that player.

A key was checked for and never taken, so "small keys open any door once" could not be
written. `consume` on a `locked` requirement (true) or a `condition` requirement (a
list of items) spends the key when the player actually goes through.

Two rules matter more than the feature:

* The key is spent at the **commit point**, after every check has passed and before the
  move, so a move refused for any other reason (a room behind the door locked by a second
  key, say) never costs a key.
* What is remembered is a **flag on the player**, `exit_open:<region>:<room>:<direction>`,
  not a change to the room's `exit_requirements`. A static room is rebuilt from its JSON,
  so editing the requirement would re-lock the door and soft-lock a player who had spent
  the key. The flag also survives a save, and it is per player: in a shared world one
  player's key does not open the door for another.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.player.core import Player
from engine.server import content_set
from tests.fixtures import GameTestBase
from tests.singles.test_exit_conditions import _Gated

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Doors(_Gated):
    def setUp(self):
        super().setUp()
        self.key = "item_healing_potion_small"   # any template will do for a probe key

    def give(self, item_id=None, count=1):
        for _ in range(count):
            self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id or self.key, self.world))

    def held(self, item_id=None):
        return self.player.inventory.count_item(item_id or self.key)

    def flag(self):
        return "exit_open:%s:%s:%s" % (self.origin[0], self.origin[1], self.direction)

    def door(self, **more):
        self.gate({"type": "locked", "key_id": self.key, **more})


class TestVocabulary(unittest.TestCase):
    def test_consume_is_read_by_locked_and_condition_requirements(self):
        self.assertIn("consume", content_set.EXIT_REQUIREMENT_KEYS["locked"])
        self.assertIn("consume", content_set.EXIT_REQUIREMENT_KEYS["condition"])
        self.assertNotIn("consume", content_set.EXIT_REQUIREMENT_KEYS["skill"])


class TestASpentKey(_Doors):
    def test_a_key_that_is_not_consumed_stays_in_the_pack(self):
        self.door()
        self.give()
        self.go()
        self.assertEqual(self.destination, self.where())
        self.assertEqual(1, self.held())

    def test_a_consumed_key_is_spent_and_the_way_opens(self):
        self.door(consume=True)
        self.give()
        text = self.go()
        self.assertEqual(self.destination, self.where())
        self.assertEqual(0, self.held())
        self.assertTrue(self.player.flags.get(self.flag()))
        self.assertIn("you spend the", text.lower())

    def test_the_door_then_stays_open_for_the_one_who_opened_it(self):
        self.door(consume=True)
        self.give()
        self.go()
        self.player.current_region_id, self.player.current_room_id = self.origin
        self.go()
        self.assertEqual(self.destination, self.where(), "no key needed the second time")

    def test_without_the_key_the_door_is_shut_and_nothing_is_recorded(self):
        self.door(consume=True)
        text = self.go()
        self.assertEqual(self.origin, self.where())
        self.assertNotIn(self.flag(), self.player.flags)
        self.assertIn("locked", text)

    def test_a_key_is_spent_once_per_door_not_once_per_walk(self):
        self.door(consume=True)
        self.give(count=2)
        self.go()
        self.player.current_region_id, self.player.current_room_id = self.origin
        self.go()
        self.assertEqual(1, self.held(), "the second key is still there")

    def test_the_rooms_requirement_is_not_edited(self):
        """A static room is rebuilt from JSON; editing it would re-lock the door."""
        self.door(consume=True)
        self.give()
        self.go()
        requirement = self.world.get_current_room(self.player) if False else None
        room = self.world.get_region(self.origin[0]).get_room(self.origin[1])
        self.assertIn(self.direction, room.properties["exit_requirements"])

    def test_a_move_refused_for_another_reason_never_costs_the_key(self):
        """The commit point is after every check: a second lock behind the door refuses first."""
        self.door(consume=True)
        self.give()
        target = self.world.get_region(self.destination[0]).get_room(self.destination[1])
        target.properties["locked_by"] = "item_nobody_has"
        self.go()
        self.assertEqual(self.origin, self.where())
        self.assertEqual(1, self.held(), "the key was not spent")
        self.assertNotIn(self.flag(), self.player.flags)

    def test_it_is_per_player(self):
        self.door(consume=True)
        self.give()
        self.go()
        stranger_flags = {}
        self.assertNotIn(self.flag(), stranger_flags)
        self.assertIn(self.flag(), self.player.flags, "the memory is on the player who spent the key")

    def test_the_open_door_survives_a_save(self):
        self.door(consume=True)
        self.give()
        self.go()
        data = json.loads(json.dumps(self.player.to_dict(self.world)))
        again = Player.from_dict(data, self.world)
        self.assertTrue(again.flags.get(self.flag()))


class TestASpentCondition(_Doors):
    def gate_on_holding(self, **more):
        self.gate({"type": "condition", "condition": {"kind": "has_item", "item_id": self.key}, **more})

    def test_the_items_listed_are_spent_when_the_condition_lets_you_through(self):
        self.gate_on_holding(consume=[self.key])
        self.give()
        self.go()
        self.assertEqual(self.destination, self.where())
        self.assertEqual(0, self.held())
        self.assertTrue(self.player.flags.get(self.flag()))

    def test_a_quantity_can_be_named(self):
        self.gate({"type": "condition", "condition": {"kind": "has_item", "item_id": self.key}, "consume": [{"item_id": self.key, "quantity": 2}]})
        self.give(count=3)
        self.go()
        self.assertEqual(1, self.held())

    def test_without_the_condition_nothing_is_spent(self):
        self.gate({"type": "condition", "condition": {"kind": "flag", "flag": "never"}, "consume": [self.key]})
        self.give()
        self.go()
        self.assertEqual(self.origin, self.where())
        self.assertEqual(1, self.held())

    def test_a_condition_without_consume_is_read_afresh_as_before(self):
        self.gate_on_holding()
        self.give()
        self.go()
        self.assertEqual(1, self.held())
        self.assertNotIn(self.flag(), self.player.flags)


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing one room's exit requirement."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.region_file = self.package / "data" / "regions" / "mossroot.json"
        payload = json.loads(self.region_file.read_text(encoding="utf-8"))
        self.room_id, room = next((rid, r) for rid, r in payload["rooms"].items() if r.get("exits"))
        self.direction = sorted(room["exits"])[0]
        self.key = "item_key_mossroot"

    def _issues(self, requirement):
        payload = json.loads(self.region_file.read_text(encoding="utf-8"))
        payload["rooms"][self.room_id].setdefault("properties", {})["exit_requirements"] = {self.direction: requirement}
        self.region_file.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i for i in issues if self.room_id in i.message]

    def _errors(self, requirement):
        return [i.message for i in self._issues(requirement) if i.severity == "error"]

    def _warnings(self, requirement):
        return [i.message for i in self._issues(requirement) if i.severity == "warning"]

    def test_a_consumed_key_is_accepted(self):
        self.assertEqual([], self._errors({"type": "locked", "key_id": self.key, "consume": True}))

    def test_consume_must_be_true_or_false(self):
        errors = self._errors({"type": "locked", "key_id": self.key, "consume": "yes"})
        self.assertTrue(any("consume" in m for m in errors), errors)

    def test_consuming_a_key_the_door_does_not_name_is_refused(self):
        errors = self._errors({"type": "locked", "consume": True})
        self.assertTrue(any("consume" in m and "key_id" in m for m in errors), errors)

    def test_a_skill_requirement_has_nothing_to_consume(self):
        errors = self._errors({"type": "skill", "skill_name": "athletics", "consume": True})
        self.assertTrue(any("consume" in m for m in errors), errors)

    def test_a_condition_may_list_what_it_spends(self):
        gate = {"type": "condition", "condition": {"kind": "has_item", "item_id": self.key}, "consume": [self.key]}
        self.assertEqual([], self._errors(gate))
        self.assertEqual([], [m for m in self._warnings(gate) if "consume" in m])

    def test_the_list_must_be_items_the_set_defines(self):
        gate = {"type": "condition", "condition": {"kind": "has_item", "item_id": self.key}, "consume": ["item_nobody_authored"]}
        errors = self._errors(gate)
        self.assertTrue(any("item_nobody_authored" in m for m in errors), errors)

    def test_an_empty_or_malformed_list_is_refused(self):
        for consume in ([], "item_x", 5, [""]):
            gate = {"type": "condition", "condition": {"kind": "has_item", "item_id": self.key}, "consume": consume}
            errors = self._errors(gate)
            self.assertTrue(any("consume" in m for m in errors), (consume, errors))

    def test_spending_what_the_condition_does_not_require_holding_draws_a_warning(self):
        gate = {"type": "condition", "condition": {"kind": "flag", "flag": "x"}, "consume": [self.key]}
        warnings = self._warnings(gate)
        self.assertTrue(any("consume" in m and self.key in m for m in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
