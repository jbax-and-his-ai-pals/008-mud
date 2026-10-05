# tests/singles/test_kill_triggers.py
"""Something can happen when a creature dies, or when the last hostile in a room does.

`npc_killed` fires when a named creature dies (by template or placed id, anywhere or in a
room); `room_cleared` when the last living hostile in a room is gone. Both need every death
to be a death:

* Only a kill by the player went through `die()`. A creature that burned, was poisoned, or
  was killed by another creature had `is_alive` cleared by `take_damage` and was then swept
  away by the world tick: no loot, no return timer for a friendly, and nothing "killed" it
  as far as a trigger could tell. The world tick now finds those deaths (the reaper),
  lets `die()` run, and raises the event once. That is a behaviour fix, and a visible one:
  a creature that dies of poison now drops what it carries.
* A summon that expires is not killed. It is released from its owner, not reaped.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.world.triggers import TRIGGER_EVENTS
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402

LOOT = "item_healing_potion_small"


class _Deaths(GameTestBase):
    def setUp(self):
        super().setUp()
        self.here = (self.player.current_region_id, self.player.current_room_id)
        for npc in [n for n in self.world.npcs.values() if (n.current_region_id, n.current_room_id) == self.here]:
            self.world.remove_npcs(npc.obj_id)   # a quiet room to test in

    def template(self, faction):
        return next(t for t, d in sorted(self.world.npc_templates.items())
                    if d.get("faction") == faction and not any(n.template_id == t for n in self.world.npcs.values()))

    def spawn(self, faction="hostile", instance_id=None, room=None):
        region, room_id = room or self.here
        npc, status = self.world.spawn_npc(self.template(faction), region, room_id, instance_id)
        self.assertEqual("spawned", status)
        return npc

    def on_kill(self, trigger_id="t", **on):
        self.world.trigger_runner.add(trigger_id, {
            "on": {"event": "npc_killed", **on}, "once": False, "effects": {"message": "It falls (%s)." % trigger_id}})

    def on_clear(self, trigger_id="c", **more):
        self.world.trigger_runner.add(trigger_id, {
            "on": {"event": "room_cleared", "region": self.here[0], "room": self.here[1]}, "once": False,
            "effects": {"message": "The room is clear."}, **more})

    def kill_in_combat(self, npc):
        """The way a player's blow ends it: the creature is dead, then the event is raised."""
        npc.take_damage(10 ** 6, "physical")
        return self.world.dispatch_event("npc_killed", {"player": self.player, "npc": npc}) or ""

    def tick(self):
        self.world.last_update_time = self.world.clock.now() - 1000
        return self.world.update()


class TestTheVocabulary(unittest.TestCase):
    def test_the_events(self):
        self.assertEqual(("on_enter", "npc_killed", "room_cleared", "item_taken", "health_below"), tuple(TRIGGER_EVENTS))


class TestNpcKilled(_Deaths):
    def test_it_fires_for_the_creature_named_by_template(self):
        npc = self.spawn()
        self.on_kill(npc=npc.template_id)
        self.assertIn("It falls", self.kill_in_combat(npc))

    def test_or_by_placed_id(self):
        npc = self.spawn(instance_id="the_named_one")
        self.on_kill(npc="the_named_one")
        self.assertIn("It falls", self.kill_in_combat(npc))

    def test_not_for_another_creature(self):
        npc = self.spawn()
        self.on_kill(npc="something_else")
        self.assertNotIn("It falls", self.kill_in_combat(npc))

    def test_a_room_narrows_it(self):
        npc = self.spawn()
        region, room = self.here
        elsewhere = next(r for r in self.world.get_region(region).rooms if r != room)
        self.on_kill(npc=npc.template_id, region=region, room=elsewhere)
        self.assertNotIn("It falls", self.kill_in_combat(npc), "it died in a different room")
        other = self.spawn(room=self.here)
        self.on_kill("t2", npc=other.template_id, region=region, room=room)
        self.assertIn("(t2)", self.kill_in_combat(other))

    def test_its_effects_can_change_the_world(self):
        npc = self.spawn()
        region, room = self.here
        direction, destination = next(iter(self.world.get_region(region).get_room(room).exits.items()))
        self.world.trigger_runner.add("close", {
            "on": {"event": "npc_killed", "npc": npc.template_id},
            "effects": {"seal_exit": {"region": region, "room": room, "direction": direction}}})
        self.kill_in_combat(npc)
        self.assertNotIn(direction, self.world.get_region(region).get_room(room).exits)


class TestRoomCleared(_Deaths):
    def test_it_fires_only_when_the_last_hostile_is_gone(self):
        first, second = self.spawn(instance_id="a"), self.spawn(instance_id="b")
        self.on_clear()
        self.assertNotIn("clear", self.kill_in_combat(first))
        self.assertIn("The room is clear.", self.kill_in_combat(second))

    def test_a_friendly_dying_does_not_clear_or_count(self):
        hostile = self.spawn(instance_id="foe")
        friend = self.spawn("friendly", instance_id="friend")
        self.on_clear()
        self.assertNotIn("clear", self.kill_in_combat(friend), "a hostile is still standing")
        self.assertIn("The room is clear.", self.kill_in_combat(hostile))

    def test_it_can_fire_again_after_the_room_fills_again(self):
        self.on_clear()
        self.assertIn("clear", self.kill_in_combat(self.spawn(instance_id="one")))
        self.assertIn("clear", self.kill_in_combat(self.spawn(instance_id="two")))

    def test_the_gate_and_the_trigger_agree(self):
        """The `room_clear` condition of 3.1 and this event ask the same question."""
        from engine.conditions import evaluate
        npc = self.spawn()
        self.assertFalse(evaluate({"kind": "room_clear"}, self.player).satisfied)
        self.kill_in_combat(npc)
        self.assertTrue(evaluate({"kind": "room_clear"}, self.player).satisfied)


class TestEveryDeathIsADeath(_Deaths):
    def test_a_creature_that_dies_of_something_else_is_reaped_and_the_event_fires_once(self):
        npc = self.spawn()
        npc.loot_table = {LOOT: {"chance": 1}}
        self.on_kill(npc=npc.template_id)
        self.on_clear()
        npc.take_damage(10 ** 6, "physical")   # poison, fire, another creature: nothing calls die()
        messages = self.tick()
        text = "\n".join(str(m) for _loc, m in messages)
        self.assertIn("It falls", text)
        self.assertIn("The room is clear.", text)
        self.assertIn(self.here, [loc for loc, _m in messages], "delivered to the room it happened in")
        self.assertTrue(any(i.obj_id == LOOT for i in self.world.get_region(self.here[0]).get_room(self.here[1]).items),
                        "and it dropped what it carried")
        self.assertNotIn("It falls", "\n".join(str(m) for _loc, m in self.tick()), "once, not every tick")

    def test_a_friendly_that_died_that_way_returns_as_a_friendly_does(self):
        friend = self.spawn("friendly", instance_id="friend_probe")
        friend.take_damage(10 ** 6, "physical")
        self.tick()
        self.assertTrue([e for e in self.world.respawn_manager.respawn_queue if e.get("instance_id") == "friend_probe"])

    def test_a_death_that_went_through_die_is_not_reaped_again(self):
        npc = self.spawn()
        self.on_kill(npc=npc.template_id)
        self.kill_in_combat(npc)
        npc.die(self.world)
        self.assertNotIn("It falls", "\n".join(str(m) for _loc, m in self.tick()))

    def test_a_summon_that_expires_is_not_killed(self):
        npc = self.spawn("friendly", instance_id="conjured")
        npc.properties["is_summoned"] = True
        self.on_kill(npc=npc.template_id)
        npc.despawn(self.world, silent=True)
        self.assertNotIn("It falls", "\n".join(str(m) for _loc, m in self.tick()))

    def test_a_removed_creature_is_not_killed(self):
        npc = self.spawn()
        self.on_kill(npc=npc.template_id)
        self.world.remove_npcs(npc.obj_id)
        self.assertNotIn("It falls", "\n".join(str(m) for _loc, m in self.tick()))


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice with a trigger file added."""

    GOOD_KILL = {"on": {"event": "npc_killed", "npc": "horned_wyrm"}, "effects": {"message": "It is done."}}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.folder = self.package / "data" / "triggers"
        self.folder.mkdir(exist_ok=True)

    def _errors(self, triggers):
        (self.folder / "kills.json").write_text(json.dumps(triggers), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_good_kill_and_clear_triggers_are_accepted(self):
        self.assertEqual([], self._errors({
            "probe_kill": self.GOOD_KILL,
            "probe_in_a_room": {"on": {"event": "npc_killed", "npc": "horned_wyrm", "region": "mossroot", "room": "boss_hall"},
                          "effects": {"message": "x"}},
            "probe_hall_clear": {"on": {"event": "room_cleared", "region": "mossroot", "room": "mossy_gallery"},
                           "effects": {"message": "x"}}}))

    def test_a_kill_trigger_needs_a_creature_the_set_defines(self):
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "npc_killed"}}})
        self.assertTrue(any("'t'" in m and "npc" in m for m in errors), errors)
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "npc_killed", "npc": "no_such_creature"}}})
        self.assertTrue(any("no_such_creature" in m for m in errors), errors)

    def test_it_may_name_a_placed_creature_too(self):
        self.assertEqual([], self._errors({"t": {**self.GOOD_KILL, "on": {"event": "npc_killed", "npc": "soldier_stair"}}}))

    def test_a_room_for_a_kill_comes_as_a_pair(self):
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "npc_killed", "npc": "horned_wyrm", "region": "mossroot"}}})
        self.assertTrue(any("'t'" in m and "region" in m and "room" in m for m in errors), errors)

    def test_a_cleared_room_trigger_needs_its_room(self):
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "room_cleared"}}})
        self.assertTrue(any("'t'" in m and ("region" in m or "room" in m) for m in errors), errors)

    def test_a_field_the_event_does_not_read_is_refused(self):
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "npc_killed", "npc": "horned_wyrm", "moon": "full"}}})
        self.assertTrue(any("'t'" in m and "moon" in m for m in errors), errors)
        errors = self._errors({"t": {**self.GOOD_KILL, "on": {"event": "room_cleared", "region": "mossroot", "room": "boss_hall", "npc": "horned_wyrm"}}})
        self.assertTrue(any("'t'" in m and "npc" in m for m in errors), errors)


if __name__ == "__main__":
    unittest.main()
