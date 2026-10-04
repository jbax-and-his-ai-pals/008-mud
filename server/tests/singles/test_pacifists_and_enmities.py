# tests/singles/test_pacifists_and_enmities.py
"""Soldiers who cut down people who do not fight back, told as ordinary combat.

Four engine pieces make that content-only: a faction enmity (`ruleset.factions.enmities`: one faction attacks another on
sight without turning on the player), the `pacifist` NPC property (never fights back, never starts a fight), the
`npc_present` condition (so a trigger can wait for the last of a kind to fall) and `opening.pace` (how fast a client
types the first-session brief). A death the player only watched fires `npc_killed` triggers and nothing else: no XP,
no quest credit, no reputation.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from engine import conditions
from engine.npcs import combat as npc_combat
from engine.server import content_set as validator
from engine.server.headless_server import HeadlessServer
from engine.world import factions
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _npc(template, obj_id, region="r", room="a", alive=True):
    return SimpleNamespace(template_id=template, obj_id=obj_id, is_alive=alive, current_region_id=region, current_room_id=room)


def _player(*npcs):
    return SimpleNamespace(world=SimpleNamespace(npcs={n.obj_id: n for n in npcs}))


class TestNpcPresent(unittest.TestCase):
    def test_a_living_npc_of_the_template_is_present_anywhere_or_in_the_room_named(self):
        player = _player(_npc("acolyte", "acolyte_1", "ilmara", "chamber"))
        self.assertTrue(conditions.evaluate({"kind": "npc_present", "npc_id": "acolyte"}, player).satisfied)
        self.assertTrue(conditions.evaluate({"kind": "npc_present", "npc_id": "acolyte_1"}, player).satisfied, "or by placed id")
        here = {"kind": "npc_present", "npc_id": "acolyte", "region_id": "ilmara", "room_id": "chamber"}
        elsewhere = {"kind": "npc_present", "npc_id": "acolyte", "region_id": "ilmara", "room_id": "stair"}
        self.assertTrue(conditions.evaluate(here, player).satisfied)
        self.assertFalse(conditions.evaluate(elsewhere, player).satisfied)

    def test_the_dead_are_not_present_so_not_it_is_true_once_the_last_is_gone(self):
        wanted = {"not": {"kind": "npc_present", "npc_id": "acolyte"}}
        self.assertFalse(conditions.evaluate(wanted, _player(_npc("acolyte", "a1"), _npc("acolyte", "a2", alive=False))).satisfied)
        self.assertTrue(conditions.evaluate(wanted, _player(_npc("acolyte", "a1", alive=False))).satisfied)
        self.assertTrue(conditions.evaluate(wanted, _player()).satisfied)


class TestEnmities(unittest.TestCase):
    def view(self, **section):
        return factions.RulesetView({"factions": section})

    def test_one_faction_attacks_another_and_it_is_not_returned(self):
        world = self.view(
            extra=[{"id": "ilmaran", "disposition": "neutral"}, {"id": "red_fleet", "disposition": "friendly"}],
            enmities=[{"faction": "red_fleet", "against": "ilmaran"}],
        )
        self.assertLess(factions.attitude(world, "red_fleet", "ilmaran"), 0)
        self.assertGreaterEqual(factions.attitude(world, "ilmaran", "red_fleet"), 0, "one way only")
        self.assertGreaterEqual(factions.attitude(world, "red_fleet", "player"), 0, "and the player is left alone")
        bystanders = self.view(extra=[{"id": "ilmaran", "disposition": "neutral"}, {"id": "red_fleet", "disposition": "friendly"}])
        self.assertEqual(0, factions.attitude(bystanders, "red_fleet", "ilmaran"), "without the declaration they ignore each other")

    def test_a_malformed_enmity_is_refused(self):
        problems = factions.issues(self.view(
            extra=[{"id": "red_fleet", "disposition": "friendly"}],
            enmities=[{"faction": "red_fleet", "against": "nobody"}, {"faction": "red_fleet", "against": "red_fleet"}, "text", {"faction": ""}],
        ))
        text = "\n".join(problems)
        self.assertIn("'nobody', which is not a declared faction", text)
        self.assertIn("an enemy of itself", text)
        self.assertIn("must be an object", text)
        self.assertIn("must name a faction", text)
        self.assertTrue(factions.issues(self.view(enmities="red_fleet")), "an enmities that is not a list is refused")


class TestPacifists(unittest.TestCase):
    def test_a_pacifist_never_enters_combat_or_attacks(self):
        from engine.npcs.npc import NPC

        peaceful = NPC(name="acolyte", health=20)
        peaceful.properties["pacifist"] = True
        soldier = NPC(name="soldier", health=70)
        npc_combat.enter_combat(soldier, peaceful)
        self.assertTrue(soldier.in_combat)
        self.assertFalse(peaceful.in_combat, "being attacked does not make a pacifist fight")
        npc_combat.enter_combat(peaceful, soldier)
        self.assertNotIn(soldier, peaceful.combat_targets)
        self.assertIsNone(npc_combat.try_attack(peaceful, None, 0.0))

    def test_the_property_must_be_true_or_false(self):
        errors = validator._npc_property_errors({"pacifist": "yes"}, "npc", set())
        self.assertTrue([e for e in errors if "pacifist must be true or false" in e])
        self.assertFalse(validator._npc_property_errors({"pacifist": True}, "npc", set()))


def _set(case):
    tmp = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    package = tmp / "story_fixture"
    shutil.copytree(STORY_FIXTURE, package)
    data = package / "data"
    people = json.loads((data / "npcs" / "people.json").read_text(encoding="utf-8"))
    base = {"description": "x", "level": 1, "behavior_type": "stationary", "properties": {"wander_chance": 0, "move_cooldown": 9999}}
    people["test_raider"] = dict(base, name="soldier", health=70, max_health=70, attack_power=8, faction="red_fleet",
                                 properties={"wander_chance": 0, "move_cooldown": 9999, "aggression": 1, "essential": True})
    people["test_acolyte"] = dict(base, name="acolyte", health=20, max_health=20, attack_power=9, faction="ilmaran",
                                  properties={"wander_chance": 0, "move_cooldown": 9999, "pacifist": True})
    (data / "npcs" / "people.json").write_text(json.dumps(people, indent=4), encoding="utf-8")
    (data / "scenes").mkdir(exist_ok=True)
    (data / "scenes" / "witness.json").write_text(json.dumps({"after_the_last": {"beats": [{"text": "The altar goes quiet."}]}}), encoding="utf-8")
    (data / "triggers" / "witness.json").write_text(json.dumps({"the_last_falls": {
        "on": {"event": "npc_killed", "npc": "test_acolyte"},
        "when": {"not": {"kind": "npc_present", "npc_id": "test_acolyte"}},
        "once": "player", "effects": {"play_scene": "after_the_last"}}}), encoding="utf-8")
    ruleset_path = package / "rules" / "ruleset.json"
    ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
    ruleset["factions"] = {"extra": [{"id": "ilmaran", "disposition": "neutral"}, {"id": "red_fleet", "disposition": "friendly"}],
                           "enmities": [{"faction": "red_fleet", "against": "ilmaran"}]}
    ruleset_path.write_text(json.dumps(ruleset, indent=2), encoding="utf-8")
    return package


class TestTheFightIsOrdinaryCombat(unittest.TestCase):
    def test_soldiers_cut_down_pacifists_who_never_strike_back_and_the_last_death_fires_the_trigger(self):
        package = _set(self)
        server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Aldric")
        player = server.get_player_for_session(sid)
        for _ in range(40):   # let the opening scene (the fixture's) finish
            server.world.clock.advance(1.0)
            server.tick(sid)
        region, room = player.current_region_id, player.current_room_id
        for number in (1, 2):
            server.world.spawn_npc("test_acolyte", region, room, "acolyte_%d" % number)
        for number in (1, 2):
            server.world.spawn_npc("test_raider", region, room, "raider_%d" % number)
        reputation_before = dict(player.reputation)
        health_before = {npc.obj_id: npc.health for npc in server.world.npcs.values() if npc.template_id == "test_raider"}

        told = []
        for _ in range(60):
            server.world.clock.advance(1.0)
            events = server.tick(sid) + server._flush_background_batch(sid)
            told += [str(e["payload"]) for e in events if e["type"] == "text"]
            if not [n for n in server.world.npcs.values() if n.template_id == "test_acolyte" and n.is_alive]:
                break
        for _ in range(6):   # and the scene it starts
            server.world.clock.advance(1.0)
            events = server.tick(sid) + server._flush_background_batch(sid)
            told += [str(e["payload"]) for e in events if e["type"] == "text"]
        text = _MARKUP.sub("", "\n".join(told))

        self.assertFalse([n for n in server.world.npcs.values() if n.template_id == "test_acolyte" and n.is_alive], "the acolytes fell")
        self.assertRegex(text, r"[Aa] soldier attacks an acolyte", "told as ordinary combat")
        self.assertNotRegex(text, r"[Aa]n acolyte attacks", "and they never fought back")
        for npc in server.world.npcs.values():
            if npc.template_id == "test_raider":
                self.assertEqual(health_before[npc.obj_id], npc.health, "the soldiers were never touched")
        self.assertEqual(reputation_before, dict(player.reputation), "watching costs the player no reputation")
        self.assertEqual(1, text.count("The altar goes quiet."), "the trigger waited for the last one, and fired once")
        self.assertIn("_scene_done.after_the_last", player.flags)


class TestOpeningPace(unittest.TestCase):
    def boot(self, opening):
        package = _set(self)
        manifest = json.loads((package / "content_set.manifest.json").read_text(encoding="utf-8"))
        path = package / manifest["paths"]["opening"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(opening)
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        return package

    def test_the_brief_is_marked_for_the_pace_the_set_names(self):
        package = self.boot({"pace": "slow"})
        server = HeadlessServer(db_path=":memory:", content_set_path=str(package), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        guidance = server.build_opening_guidance()
        self.assertTrue(guidance.startswith("[[PACE:70]]") and guidance.endswith("[[/PACE]]"), guidance[:40])

    def test_no_pace_is_the_brief_as_it_was(self):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(self.boot({})), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        self.assertNotIn("[[PACE", server.build_opening_guidance())

    def test_a_pace_that_is_not_one_is_refused(self):
        _definition, issues = validator.load_content_set(self.boot({"pace": "glacial"}))
        self.assertTrue([i for i in issues if i.severity == "error" and "opening pace 'glacial'" in i.message], [i.message for i in issues])


if __name__ == "__main__":
    unittest.main()
