# tests/singles/test_npc_effects.py
"""A conversation can bring an NPC into the world and take one out of it.

`move_npc` could only shuffle the cast. A masked advisor who is really a fiend, a
hermit who was never quite there: those need an NPC to appear and to vanish.
`spawn_npc` places one from a template, and `remove_npc` takes one out without it
*dying* -- no loot, no respawn timer, no kill counted -- because a character that
was never killed must not be treated as though it were. Both survive a restart,
because the world snapshot keeps whole NPCs and a removed one is simply not in it.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.dialogue.effects import KNOWN_EFFECTS, apply_effects
from engine.npcs.npc import NPC
from engine.world import world_snapshot
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Npcs(GameTestBase):
    def setUp(self):
        super().setUp()
        # A template nobody has placed yet, so a count means what the test made.
        self.template = next(t for t, _d in sorted(self.world.npc_templates.items()) if not self.alive(t))

    def apply(self, effects):
        return apply_effects(effects, {"player": self.player, "world": self.world})

    @property
    def here(self):
        return self.player.current_region_id, self.player.current_room_id

    def alive(self, template_id):
        return [npc for npc in self.world.npcs.values() if npc.template_id == template_id and npc.is_alive]

    def spawn_effect(self, **more):
        region, room = self.here
        return {"spawn_npc": {"npc": self.template, "region": region, "room": room, **more}}


class TestTheVocabulary(unittest.TestCase):
    def test_both_effects_are_known(self):
        self.assertIn("spawn_npc", KNOWN_EFFECTS)
        self.assertIn("remove_npc", KNOWN_EFFECTS)


class TestSpawning(_Npcs):
    def test_an_npc_appears_in_the_room_named(self):
        report = self.apply(self.spawn_effect())
        made = self.alive(self.template)
        self.assertEqual(1, len(made), report.summary())
        self.assertEqual(self.here, (made[0].current_region_id, made[0].current_room_id))
        self.assertEqual(self.here, (made[0].home_region_id, made[0].home_room_id), "and calls it home")
        self.assertTrue(report.applied, report.summary())

    def test_it_is_a_full_member_of_the_world(self):
        self.apply(self.spawn_effect())
        made = self.alive(self.template)[0]
        self.assertIs(self.world.get_npc(made.obj_id), made)
        self.assertIn(made, self.world.get_npcs_in_room(*self.here))
        self.assertIs(self.world, made.world)

    def test_asking_twice_does_not_make_two(self):
        """A conversation can be had again, so the same request must be safe."""
        self.apply(self.spawn_effect())
        report = self.apply(self.spawn_effect())
        self.assertEqual(1, len(self.alive(self.template)))
        self.assertEqual([], report.applied)
        self.assertTrue(report.unchanged, report.summary())

    def test_an_id_can_be_given(self):
        self.apply(self.spawn_effect(instance_id="rat_of_the_cellar"))
        self.assertIsNotNone(self.world.get_npc("rat_of_the_cellar"))

    def test_a_template_nobody_authored_is_reported(self):
        region, room = self.here
        report = self.apply({"spawn_npc": {"npc": "no_such_creature", "region": region, "room": room}})
        self.assertTrue(any("no_such_creature" in failure for failure in report.failed), report.summary())

    def test_a_room_that_does_not_exist_is_reported_and_nothing_appears(self):
        before = set(self.world.npcs)
        report = self.apply({"spawn_npc": {"npc": self.template, "region": "nowhere", "room": "nothing"}})
        self.assertTrue(report.failed, report.summary())
        self.assertEqual(before, set(self.world.npcs))


class TestRemoving(_Npcs):
    def setUp(self):
        super().setUp()
        self.apply(self.spawn_effect(instance_id="rat_one"))
        self.apply(self.spawn_effect(instance_id="rat_two"))

    def test_by_template_id_every_match_goes(self):
        report = self.apply({"remove_npc": self.template})
        self.assertEqual([], self.alive(self.template))
        self.assertTrue(report.applied, report.summary())

    def test_by_instance_id_only_that_one_goes(self):
        self.apply({"remove_npc": "rat_one"})
        self.assertIsNone(self.world.get_npc("rat_one"))
        self.assertIsNotNone(self.world.get_npc("rat_two"))

    def test_a_room_can_narrow_it(self):
        region, room = self.here
        other = next(r for r in self.world.get_region(region).rooms if r != room)
        self.apply({"remove_npc": {"npc": self.template, "region": region, "room": other}})
        self.assertEqual(2, len(self.alive(self.template)), "none were in that room")
        self.apply({"remove_npc": {"npc": self.template, "region": region, "room": room}})
        self.assertEqual([], self.alive(self.template))

    def test_nothing_there_is_nothing_to_do_not_a_failure(self):
        report = self.apply({"remove_npc": "no_such_creature"})
        self.assertEqual([], report.applied)
        self.assertEqual([], report.failed)
        self.assertTrue(report.unchanged, report.summary())

    def test_it_is_not_a_death(self):
        """No loot, no respawn timer, and `die()` is never asked."""
        queue_before = list(self.world.respawn_manager.respawn_queue)
        items_before = list(self.world.get_region(self.here[0]).get_room(self.here[1]).items)
        with mock.patch.object(NPC, "die", side_effect=AssertionError("removal is not a death")):
            self.apply({"remove_npc": self.template})
        self.assertEqual([], self.alive(self.template), "they are gone")
        self.assertEqual(queue_before, self.world.respawn_manager.respawn_queue)
        self.assertEqual(items_before, list(self.world.get_region(self.here[0]).get_room(self.here[1]).items))

    def test_a_pending_return_of_the_same_creature_is_cancelled(self):
        """`remove_npc: hermit` after the hermit was killed must not let the hermit return later."""
        self.world.respawn_manager.respawn_queue.append({
            "template_id": self.template, "instance_id": "rat_dead_earlier", "name": "giant rat",
            "home_region_id": self.here[0], "home_room_id": self.here[1], "respawn_time": 10 ** 9,
        })
        report = self.apply({"remove_npc": self.template})
        self.assertEqual([], [e for e in self.world.respawn_manager.respawn_queue if e["template_id"] == self.template])
        self.assertTrue(report.applied, report.summary())


class TestSurvivingARestart(_Npcs):
    def test_a_spawned_npc_and_a_removed_one_are_what_a_restore_gives_back(self):
        region, room = self.here
        self.apply(self.spawn_effect(instance_id="rat_spawned"))
        victim = next(iter(n for n in self.world.npcs.values() if n.is_alive and n.obj_id != "rat_spawned"))
        self.apply({"remove_npc": victim.obj_id})
        snapshot = copy.deepcopy(world_snapshot.capture(self.world))
        json.loads(json.dumps(snapshot))   # it must be savable

        world_snapshot.restore(self.world, snapshot)
        self.assertIsNotNone(self.world.get_npc("rat_spawned"), "the spawned NPC is still there")
        self.assertIsNone(self.world.get_npc(victim.obj_id), "and the removed one is still gone")


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing only its hermit's conversation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.graph = self.package / "data" / "dialogue" / "hermit_gift.json"

    def _errors(self, effects):
        payload = json.loads(self.graph.read_text(encoding="utf-8"))
        payload["nodes"]["greeting"]["choices"][0]["effects"] = effects
        self.graph.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error" and "hermit_gift" in i.message]

    def test_a_good_spawn_and_removal_are_accepted(self):
        errors = self._errors({
            "spawn_npc": {"npc": "slime_blob", "region": "caves", "room": "hermit_cave"},
            "remove_npc": "hermit",
        })
        self.assertEqual([], errors)

    def test_a_removal_may_name_a_placed_instance(self):
        self.assertEqual([], self._errors({"remove_npc": "hermit_at_hermit_cave"}))

    def test_a_removal_may_narrow_to_a_room(self):
        self.assertEqual([], self._errors({"remove_npc": {"npc": "hermit", "region": "caves", "room": "hermit_cave"}}))

    def test_a_template_nobody_authored_is_refused(self):
        errors = self._errors({"spawn_npc": {"npc": "no_such_creature", "region": "caves", "room": "hermit_cave"}})
        self.assertTrue(any("no_such_creature" in m for m in errors), errors)

    def test_a_region_or_room_nobody_authored_is_refused(self):
        errors = self._errors({"spawn_npc": {"npc": "slime_blob", "region": "nowhere", "room": "hermit_cave"}})
        self.assertTrue(any("nowhere" in m for m in errors), errors)
        errors = self._errors({"spawn_npc": {"npc": "slime_blob", "region": "caves", "room": "no_such_room"}})
        self.assertTrue(any("no_such_room" in m for m in errors), errors)

    def test_a_removal_of_nobody_the_set_defines_is_refused(self):
        errors = self._errors({"remove_npc": "no_such_creature"})
        self.assertTrue(any("no_such_creature" in m for m in errors), errors)

    def test_a_spawn_needs_a_place_and_a_removal_needs_both_or_neither(self):
        errors = self._errors({"spawn_npc": {"npc": "slime_blob"}})
        self.assertTrue(any("spawn_npc" in m and ("region" in m or "room" in m) for m in errors), errors)
        errors = self._errors({"remove_npc": {"npc": "hermit", "region": "caves"}})
        self.assertTrue(any("remove_npc" in m and "together" in m for m in errors), errors)


if __name__ == "__main__":
    unittest.main()
