# tests/singles/test_health_below.py
"""The `health_below` trigger event and the `end_fight` effect: a duel the hero cannot win, a boss that yields.

`{"event": "health_below", "who": "player" | <npc id>, "fraction": 0.25}` fires as a blow takes `who` past that share of its
health, once per crossing, and only for `who`; a heal back above it does not fire it; a room may narrow it. `end_fight` makes
everyone in a room stop fighting.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.npcs.combat import enter_combat
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")


class _Duel(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = ROOM
        self.player.health = self.player.max_health = 100
        self.world.pending_player_notices.clear()

    def foe(self, instance_id="duellist"):
        npc = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id=instance_id)
        npc.current_region_id, npc.current_room_id = ROOM
        npc.max_health = npc.health = 100
        npc.stats["defense"] = 0
        npc.properties["defense"] = 0
        self.world.add_npc(npc)
        return npc

    def trigger(self, tid="t", **on):
        self.world.trigger_runner.add(tid, {"on": dict({"event": "health_below"}, **on), "once": False,
                                            "effects": {"message": "(%s)" % tid}})

    def told(self):
        text = " ".join(t for _, t in self.world.pending_player_notices)
        self.world.pending_player_notices.clear()
        return text


class TestTheEvent(_Duel):
    def test_it_fires_for_the_player_as_a_blow_crosses_the_line(self):
        self.trigger(who="player", fraction=0.5)
        self.player.take_damage(40, "physical")
        self.assertEqual("", self.told(), "not yet: still above half")
        self.player.health = 60
        self.player.take_damage(30, "physical")
        self.assertIn("(t)", self.told())

    def test_not_again_while_it_stays_below(self):
        self.trigger(who="player", fraction=0.5)
        self.player.health = 40
        self.player.take_damage(5, "physical")
        self.assertEqual("", self.told(), "it was already below the line")

    def test_it_fires_for_a_creature_by_template_or_placed_id(self):
        goblin = self.foe()
        self.trigger("by_template", who=goblin.template_id, fraction=0.5)
        self.trigger("by_id", who="duellist", fraction=0.5)
        self.trigger("other", who="someone_else", fraction=0.5)
        goblin.health = 60
        goblin.take_damage(30, "physical")
        said = self.told()
        self.assertIn("(by_template)", said)
        self.assertIn("(by_id)", said)
        self.assertNotIn("(other)", said)

    def test_it_is_for_who_it_names_not_the_other_side(self):
        goblin = self.foe()
        self.trigger("p", who="player", fraction=0.5)
        goblin.health = 60
        goblin.take_damage(30, "physical")
        self.assertEqual("", self.told())

    def test_a_heal_back_above_does_not_fire_it_but_the_next_blow_does(self):
        self.trigger(who="player", fraction=0.5)
        self.player.health = 45
        self.player.take_damage(1, "physical")
        self.told()
        self.player.health = 80
        self.player.take_damage(40, "physical")
        self.assertIn("(t)", self.told(), "a second crossing fires it again, for a trigger that repeats")

    def test_a_room_narrows_it(self):
        self.trigger(who="player", fraction=0.5, region="hazevale", room="shrine")
        self.player.health = 60
        self.player.take_damage(30, "physical")
        self.assertEqual("", self.told(), "the player is in the square")


class TestEndFight(_Duel):
    def test_everyone_in_the_room_stops_fighting(self):
        goblin = self.foe()
        enter_combat(goblin, self.player)
        self.assertTrue(goblin.in_combat)
        apply_effects({"end_fight": {}}, {"player": self.player, "world": self.world})
        self.assertFalse(goblin.in_combat)
        self.assertFalse(self.player.runtime_state.combat.in_combat)
        self.assertEqual(set(), set(self.player.runtime_state.combat.targets))

    def test_a_named_room_is_ended_instead(self):
        goblin = self.foe()
        enter_combat(goblin, self.player)
        apply_effects({"end_fight": {"region": "hazevale", "room": "shrine"}}, {"player": self.player, "world": self.world})
        self.assertTrue(goblin.in_combat, "the fight was not in the shrine")


class TestTheValidator(unittest.TestCase):
    def errors(self, on):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        folder = pkg / "data" / "triggers"
        folder.mkdir(exist_ok=True)
        (folder / "duel.json").write_text(json.dumps({"duel": {"on": dict({"event": "health_below"}, **on), "effects": {"message": "x"}}}), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def test_good_ones_pass(self):
        self.assertEqual([], [m for m in self.errors({"who": "player", "fraction": 0.25}) if "duel" in m])
        self.assertEqual([], [m for m in self.errors({"who": "goblin_scout", "fraction": 0.5}) if "duel" in m])

    def test_bad_ones_are_refused(self):
        cases = ({"who": "player"}, {"fraction": 0.5}, {"who": "player", "fraction": 0}, {"who": "player", "fraction": 1},
                 {"who": "player", "fraction": "half"}, {"who": "nobody", "fraction": 0.5})
        for on in cases:
            self.assertTrue([m for m in self.errors(on) if "duel" in m], on)


if __name__ == "__main__":
    unittest.main()
