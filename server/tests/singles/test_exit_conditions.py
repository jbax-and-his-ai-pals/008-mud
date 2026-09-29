# tests/singles/test_exit_conditions.py
"""An exit can be gated on anything a condition can say, not only a key or a skill roll.

Exits gated on a held key or a skill roll and nothing else: no flag, no quest, no "the
room behind you is cleared". So a kill-all shutter room, a gate that opens once the king
has spoken, or a door for the knight who has earned the title could not be written. A
`condition` requirement reuses the condition language dialogue and titles already use,
and `room_clear` is the condition kill-all rooms need: no living hostile is left in it.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.conditions import KNOWN_KINDS
from engine.server import content_set
from engine.world import factions
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402

FLAG_GATE = {"type": "condition", "condition": {"kind": "flag", "flag": "may_pass"}, "failure_message": "The gate stays shut."}


class _Gated(GameTestBase):
    def setUp(self):
        super().setUp()
        room = self.world.get_current_room(self.player)
        self.direction, destination = next(
            (d, dest) for d, dest in sorted(room.exits.items())
            if ":" not in dest and self.world.get_region(self.player.current_region_id).get_room(dest)
        )
        self.origin = (self.player.current_region_id, self.player.current_room_id)
        self.destination = (self.player.current_region_id, destination)

    def gate(self, requirement):
        self.world.get_current_room(self.player).properties["exit_requirements"] = {self.direction: requirement}

    def go(self):
        return self.world.change_room(self.direction, self.player)

    def where(self):
        return (self.player.current_region_id, self.player.current_room_id)

    def hostile_template(self):
        return next(t for t, d in sorted(self.world.npc_templates.items())
                    if d.get("faction") == "hostile"
                    and not any(n.template_id == t and n.is_alive for n in self.world.npcs.values()))


class TestTheVocabulary(unittest.TestCase):
    def test_room_clear_is_a_condition_kind(self):
        self.assertIn("room_clear", KNOWN_KINDS)

    def test_the_requirement_keys_are_published(self):
        self.assertIn("condition", content_set.EXIT_REQUIREMENT_KEYS)
        self.assertEqual(("type", "condition", "failure_message"), content_set.EXIT_REQUIREMENT_KEYS["condition"])
        self.assertIn("clear_exit_req", content_set.ENV_INTERACTION_KEYS)


class TestAConditionGate(_Gated):
    def test_the_way_is_shut_until_the_condition_holds(self):
        self.gate(FLAG_GATE)
        text = self.go()
        self.assertEqual(self.origin, self.where())
        self.assertIn("The gate stays shut.", text)
        self.player.flags["may_pass"] = True
        self.go()
        self.assertEqual(self.destination, self.where())

    def test_it_is_read_afresh_each_time(self):
        self.gate(FLAG_GATE)
        self.player.flags["may_pass"] = True
        self.go()
        self.player.current_region_id, self.player.current_room_id = self.origin
        self.player.flags["may_pass"] = False
        self.go()
        self.assertEqual(self.origin, self.where(), "a condition that stopped holding shuts the way again")

    def test_without_a_message_it_says_what_is_missing(self):
        self.gate({"type": "condition", "condition": {"kind": "flag", "flag": "may_pass"}})
        text = self.go()
        self.assertEqual(self.origin, self.where())
        self.assertIn(self.direction, text)

    def test_a_condition_can_be_a_tree(self):
        self.gate({"type": "condition", "condition": {"all": [
            {"kind": "flag", "flag": "a"}, {"not": {"kind": "flag", "flag": "b"}}]}})
        self.player.flags["a"] = True
        self.go()
        self.assertEqual(self.destination, self.where())

    def test_a_condition_the_engine_cannot_read_fails_closed(self):
        self.gate({"type": "condition", "condition": {"kind": "moon_is_full"}})
        self.go()
        self.assertEqual(self.origin, self.where(), "a typo must not open a gate")

    def test_an_empty_condition_is_not_a_gate_that_is_open_to_all_by_accident(self):
        """`evaluate({})` is satisfied, so the validator refuses one; at run time it is open."""
        self.gate({"type": "condition", "condition": {}})
        self.go()
        self.assertEqual(self.destination, self.where())

    def test_a_key_gate_still_works_beside_it(self):
        self.gate({"type": "locked", "key_id": "item_nobody_has"})
        self.go()
        self.assertEqual(self.origin, self.where())


class TestRoomClear(_Gated):
    def evaluate(self, **fields):
        from engine.conditions import evaluate
        return evaluate({"kind": "room_clear", **fields}, self.player)

    def spawn(self, instance_id="probe_hostile"):
        template = self.hostile_template()
        npc, status = self.world.spawn_npc(template, *self.origin, instance_id=instance_id)
        self.assertEqual("spawned", status)
        self.assertTrue(factions.is_hostile(npc, self.world), "the probe is a hostile")
        return npc

    def test_a_room_with_no_hostile_is_clear(self):
        for npc in [n for n in self.world.npcs.values()
                    if (n.current_region_id, n.current_room_id) == self.origin and factions.is_hostile(n, self.world)]:
            self.world.remove_npcs(npc.obj_id)
        self.assertTrue(self.evaluate().satisfied)

    def test_a_living_hostile_keeps_it_shut_and_says_so(self):
        self.spawn()
        result = self.evaluate()
        self.assertFalse(result.satisfied)
        self.assertTrue(any("hostile" in reason or "foe" in reason or "enem" in reason for reason in result.reasons), result.reasons)

    def test_a_dead_hostile_does_not_count(self):
        npc = self.spawn()
        npc.is_alive = False
        self.assertTrue(self.evaluate().satisfied)

    def test_a_friendly_does_not_count(self):
        friendly = next(t for t, d in sorted(self.world.npc_templates.items())
                        if d.get("faction") == "friendly" and not any(n.template_id == t for n in self.world.npcs.values()))
        self.world.spawn_npc(friendly, *self.origin, instance_id="probe_friend")
        self.assertTrue(self.evaluate().satisfied)

    def test_it_can_name_another_room(self):
        self.spawn()
        elsewhere = self.destination
        self.assertTrue(self.evaluate(region_id=elsewhere[0], room_id=elsewhere[1]).satisfied)
        self.assertFalse(self.evaluate(region_id=self.origin[0], room_id=self.origin[1]).satisfied)

    def test_a_kill_all_shutter_opens_when_the_room_is_cleared(self):
        npc = self.spawn()
        self.gate({"type": "condition", "condition": {"kind": "room_clear", "region_id": self.origin[0], "room_id": self.origin[1]},
                   "failure_message": "The shutters are down. Something in here is still alive."})
        self.assertIn("shutters", self.go())
        self.assertEqual(self.origin, self.where())
        self.world.remove_npcs(npc.obj_id)
        self.go()
        self.assertEqual(self.destination, self.where())


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing one room's exit requirement."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.region_file = self.package / "data" / "regions" / "mossroot.json"
        payload = json.loads(self.region_file.read_text(encoding="utf-8"))
        self.room_id, self.room = next((rid, r) for rid, r in payload["rooms"].items() if r.get("exits"))
        self.direction = sorted(self.room["exits"])[0]

    def _issues(self, requirement, reactions=None):
        payload = json.loads(self.region_file.read_text(encoding="utf-8"))
        properties = payload["rooms"][self.room_id].setdefault("properties", {})
        properties["exit_requirements"] = {self.direction: requirement}
        if reactions is not None:
            properties["env_interactions"] = reactions
        self.region_file.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i for i in issues if self.room_id in i.message]

    def _errors(self, requirement, **kwargs):
        return [i.message for i in self._issues(requirement, **kwargs) if i.severity == "error"]

    def test_a_good_condition_requirement_is_accepted(self):
        self.assertEqual([], self._errors(FLAG_GATE))

    def test_a_kill_all_shutter_is_accepted(self):
        gate = {"type": "condition", "condition": {"kind": "room_clear", "region_id": "mossroot", "room_id": self.room_id}}
        self.assertEqual([], self._errors(gate))

    def test_the_type_message_still_says_a_wrong_type_leaves_the_way_open(self):
        errors = self._errors({"type": "riddle"})
        self.assertTrue(any("leaves the way open" in m for m in errors), errors)

    def test_a_condition_is_required_and_may_not_be_empty(self):
        for requirement in ({"type": "condition"}, {"type": "condition", "condition": {}}):
            errors = self._errors(requirement)
            self.assertTrue(any("condition" in m and ("required" in m or "empty" in m) for m in errors), errors)

    def test_a_condition_kind_the_engine_cannot_read_is_refused(self):
        errors = self._errors({"type": "condition", "condition": {"kind": "moon_is_full"}})
        self.assertTrue(any("moon_is_full" in m for m in errors), errors)

    def test_an_item_the_set_does_not_define_is_refused(self):
        errors = self._errors({"type": "condition", "condition": {"kind": "has_item", "item_id": "item_nobody_authored"}})
        self.assertTrue(any("item_nobody_authored" in m for m in errors), errors)

    def test_a_room_clear_for_a_room_that_does_not_exist_is_refused(self):
        errors = self._errors({"type": "condition", "condition": {"kind": "room_clear", "region_id": "mossroot", "room_id": "no_such_room"}})
        self.assertTrue(any("no_such_room" in m for m in errors), errors)
        errors = self._errors({"type": "condition", "condition": {"kind": "room_clear", "region_id": "mossroot"}})
        self.assertTrue(any("room_clear" in m and "together" in m for m in errors), errors)

    def test_a_key_the_requirement_does_not_read_is_refused(self):
        errors = self._errors({"type": "condition", "condition": {"kind": "flag", "flag": "x"}, "key_id": "item_x"})
        self.assertTrue(any("key_id" in m for m in errors), errors)

    def test_an_element_that_clears_a_condition_gate_draws_a_warning(self):
        issues = self._issues(FLAG_GATE, reactions={"fire": {"type": "clear_exit_req", "direction": self.direction}})
        warnings = [i.message for i in issues if i.severity == "warning"]
        self.assertTrue(any("clear_exit_req" in m and "condition" in m for m in warnings), [i.message for i in issues])


if __name__ == "__main__":
    unittest.main()
