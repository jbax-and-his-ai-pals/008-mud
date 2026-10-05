# tests/singles/test_combat_pacing_and_detail.py
"""How a fight reads: its rhythm (`combat.pacing`) and how much of it a player is shown (`combat detail`).

Pacing: every creature but the player acts on its cooldown stretched by `npc_cooldown_scale`, and no two creatures
act in the same room within `action_gap` seconds of each other. A world with no `pacing` section is unchanged.

Detail: `full` is every line (and the default), `normal` folds routine blows into a short summary, `brief` drops them;
a blow at the player, a death, a spell and a friend in trouble are always told in full.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.npcs import combat_detail, companions, pacing
from engine.npcs.combat import enter_combat, try_attack
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")


class _Fight(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = ROOM
        # the content set is shared between tests: put its ruleset back as it was
        combat = self.world.content_set.ruleset.setdefault("combat", {})
        had = "pacing" in combat
        before = combat.get("pacing")
        self.addCleanup(lambda: combat.__setitem__("pacing", before) if had else combat.pop("pacing", None))

    def pacing(self, **values):
        self.world.content_set.ruleset.setdefault("combat", {})["pacing"] = values

    def goblin(self, name):
        npc = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id=name)
        npc.current_region_id, npc.current_room_id = ROOM
        npc.combat_cooldown = npc.attack_cooldown = 3.0
        self.world.add_npc(npc)
        enter_combat(npc, self.player)
        npc.combat_targets = {self.player}
        npc.combat_target = self.player
        npc.last_combat_action = npc.last_attack_time = 0   # ready to strike the moment the test says so
        return npc

    def ryn(self):
        ryn = NPCFactory.create_npc_from_template("ryn", self.world, instance_id="ryn_in_party")
        ryn.current_region_id, ryn.current_room_id = ROOM
        self.world.add_npc(ryn)
        companions.recruit(self.world, self.player, ryn)
        self.world.pending_player_notices.clear()   # the recruiting is not what is under test
        return ryn


class TestPacing(_Fight):
    def test_a_world_with_no_pacing_section_is_unchanged(self):
        self.assertEqual((1.0, 0.0), pacing.settings(self.world))

    def test_the_scale_stretches_every_creatures_pause_between_blows(self):
        self.pacing(npc_cooldown_scale=2.0)
        npc = self.goblin("slow")
        self.assertIsNotNone(try_attack(npc, self.world, 1000.0), "its first blow")
        self.assertIsNone(try_attack(npc, self.world, 1004.0), "three seconds became six")
        self.assertIsNotNone(try_attack(npc, self.world, 1006.5))

    def test_without_the_scale_the_same_pause_is_three_seconds(self):
        npc = self.goblin("quick")
        self.assertIsNotNone(try_attack(npc, self.world, 1000.0))
        self.assertIsNotNone(try_attack(npc, self.world, 1003.5))

    def test_creatures_in_one_room_take_the_beat_in_turn(self):
        self.pacing(action_gap=2.0)
        first, second = self.goblin("first"), self.goblin("second")
        self.assertIsNotNone(try_attack(first, self.world, 1000.0))
        self.assertIsNone(try_attack(second, self.world, 1000.5), "the room's beat is taken")
        self.assertIsNotNone(try_attack(second, self.world, 1002.0), "and free again two seconds on")

    def test_with_no_gap_they_act_together_as_they_always_did(self):
        first, second = self.goblin("first"), self.goblin("second")
        self.assertIsNotNone(try_attack(first, self.world, 1000.0))
        self.assertIsNotNone(try_attack(second, self.world, 1000.0))

    def test_another_rooms_beat_does_not_hold_this_one(self):
        self.pacing(action_gap=5.0)
        first, second = self.goblin("first"), self.goblin("second")
        self.assertIsNotNone(try_attack(first, self.world, 1000.0))
        self.world.combat_beats[("elsewhere", "room")] = 1000.0
        self.assertIsNone(try_attack(second, self.world, 1001.0))


class TestTheValidator(unittest.TestCase):
    def errors(self, pacing_section):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        path = pkg / "rules" / "ruleset.json"
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        ruleset.setdefault("combat", {})["pacing"] = pacing_section
        path.write_text(json.dumps(ruleset), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]

    def test_good_values_pass(self):
        self.assertEqual([], [m for m in self.errors({"npc_cooldown_scale": 1.5, "action_gap": 1.2}) if "pacing" in m])

    def test_bad_values_are_refused(self):
        for bad in ({"npc_cooldown_scale": 0.5}, {"npc_cooldown_scale": "slow"}, {"action_gap": -1}, {"action_gap": 99}, {"tempo": 2}):
            self.assertTrue([m for m in self.errors(bad) if "combat.pacing" in m], bad)

    def test_it_must_be_an_object(self):
        self.assertTrue([m for m in self.errors(3) if "combat.pacing must be an object" in m])


class TestDetail(_Fight):
    def blow(self, damage=7):
        return {"message": "a blow lands.", "target_defeated": False, "routine": True, "damage": damage}

    def test_every_player_starts_at_full_and_nothing_is_written(self):
        self.assertEqual("full", combat_detail.level_of(self.player))
        self.assertNotIn(combat_detail.FLAG, self.player.flags)

    def test_the_combat_command_sets_it_and_it_is_kept_with_the_character(self):
        self.assertIn("short summaries", " ".join(str(e["payload"]) for e in self.server.execute_command(self.sid, "combat normal")))
        self.assertEqual("normal", combat_detail.level_of(self.player))
        self.assertEqual("normal", self.player.flags[combat_detail.FLAG])
        self.server.execute_command(self.sid, "combat full")
        self.assertNotIn(combat_detail.FLAG, self.player.flags, "back at the default it writes nothing")
        said = " ".join(str(e["payload"]) for e in self.server.execute_command(self.sid, "combat loud"))
        self.assertIn("one of: full, normal, brief", said)

    def test_full_tells_every_blow(self):
        ryn, goblin = self.ryn(), self.goblin("g1")
        self.assertEqual("a blow lands.", combat_detail.shape(self.world, self.player, ryn, goblin, self.blow(), "a blow lands.", 10.0))

    def test_normal_folds_routine_blows_into_one_summary(self):
        combat_detail.set_level(self.player, "normal")
        ryn, goblin = self.ryn(), self.goblin("g1")
        self.assertIsNone(combat_detail.shape(self.world, self.player, ryn, goblin, self.blow(7), "ryn hits", 10.0))
        self.assertIsNone(combat_detail.shape(self.world, self.player, goblin, ryn, self.blow(3), "goblin hits", 11.0))
        combat_detail.flush_due(self.world, 11.5)
        self.assertEqual([], self.world.pending_player_notices, "not before the window is up")
        combat_detail.flush_due(self.world, 14.0)
        (viewer, text), = self.world.pending_player_notices
        self.assertIs(self.player, viewer)
        self.assertIn("for 7.", text)
        self.assertIn("for 3.", text, "the numbers stay in the text")

    def test_a_blow_at_the_player_and_a_death_are_never_folded(self):
        combat_detail.set_level(self.player, "brief")
        goblin = self.goblin("g1")
        self.assertEqual("ouch", combat_detail.shape(self.world, self.player, goblin, self.player, self.blow(), "ouch", 10.0))
        ryn = self.ryn()
        dead = dict(self.blow(), target_defeated=True)
        self.assertEqual("it falls", combat_detail.shape(self.world, self.player, ryn, goblin, dead, "it falls", 11.0))

    def test_a_spell_is_always_told(self):
        combat_detail.set_level(self.player, "brief")
        ryn, goblin = self.ryn(), self.goblin("g1")
        spell = {"message": "Ryn calls the lightning.", "target_defeated": False}
        self.assertEqual("Ryn calls the lightning.", combat_detail.shape(self.world, self.player, ryn, goblin, spell, "Ryn calls the lightning.", 10.0))

    def test_a_friend_in_trouble_is_told_in_full(self):
        combat_detail.set_level(self.player, "brief")
        ryn, goblin = self.ryn(), self.goblin("g1")
        ryn.health = int(ryn.max_health * 0.2)
        self.assertEqual("ryn reels", combat_detail.shape(self.world, self.player, goblin, ryn, self.blow(), "ryn reels", 10.0))

    def test_brief_drops_routine_blows_and_tells_nothing_of_them_later(self):
        combat_detail.set_level(self.player, "brief")
        ryn, goblin = self.ryn(), self.goblin("g1")
        self.assertIsNone(combat_detail.shape(self.world, self.player, ryn, goblin, self.blow(), "ryn hits", 10.0))
        combat_detail.flush_due(self.world, 99.0)
        self.assertEqual([], self.world.pending_player_notices)

    def test_what_came_before_a_notable_line_is_told_first_so_the_order_is_true(self):
        combat_detail.set_level(self.player, "normal")
        ryn, goblin = self.ryn(), self.goblin("g1")
        combat_detail.shape(self.world, self.player, ryn, goblin, self.blow(7), "ryn hits", 10.0)
        told = combat_detail.shape(self.world, self.player, goblin, self.player, self.blow(), "goblin hits you", 11.0)
        self.assertTrue(told.endswith("goblin hits you"))
        self.assertIn("for 7.", told.split("\n")[0])
        combat_detail.flush_due(self.world, 99.0)
        self.assertEqual([], self.world.pending_player_notices, "and it is not told twice")

    def test_one_line_per_creature_affected_becomes_one_line(self):
        said = "The room grows heavy.\na grub (Level 6, 50/50 HP) is affected by Sleep.\na grub (Level 6, 40/50 HP) is affected by Sleep."
        self.assertEqual("The room grows heavy.\n2 enemies are affected by Sleep.", combat_detail.fold_effects(said))
        single = "a grub is affected by Sleep."
        self.assertEqual(single, combat_detail.fold_effects(single), "one is left as it is")


if __name__ == "__main__":
    unittest.main()
