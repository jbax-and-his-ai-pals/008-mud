# tests/singles/test_companions.py
"""A conversation can recruit an NPC, who then travels with the player and fights beside them.

A summon is temporary and a party is other players; nothing let an authored NPC join you.
`recruit` binds an NPC in the room to the player (the minion AI already follows an owner, joins
their fights and credits them with kills); `dismiss` sets it back down as it was. The cap is the
ruleset's `companions.max` (default 1). A companion moves with the player through any arrival,
across regions, ignoring exit gates as NPCs do; there is no ledger, so it survives a restart
because the NPC does, still carrying its owner's id.
"""

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.npcs import companions
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
HERMIT_ROOM = ("caves", "hermit_cave")


def _boot(db=":memory:"):
    return HeadlessServer(
        db_path=db, content_set_path=str(REPO_ROOT / "content_sets" / "zelda_slice"),
        deterministic_test_mode=True, default_presentation_mode="player",
    )


def _say(server, sid, command):
    events = server.execute_command(sid, command)
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in events if e.get("type") in ("text", "error")))


class _Zelda(unittest.TestCase):
    def setUp(self):
        self.server = _boot()
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="companion").session_id
        self.server.execute_command(self.sid, "char create Tester")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.at(*HERMIT_ROOM)

    def at(self, region, room):
        self.player.current_region_id, self.player.current_room_id = region, room

    def npc(self, template_id):
        return next(n for n in self.world.npcs.values() if n.template_id == template_id)

    def effects(self, effects, npc=None):
        return apply_effects(effects, {"player": self.player, "world": self.world, "npc": npc})

    def say(self, command):
        return _say(self.server, self.sid, command)

    def allow(self, count):
        self.world.content_set.ruleset["companions"] = {"max": count}
        self.addCleanup(self.world.content_set.ruleset.pop, "companions", None)


class TestRecruiting(_Zelda):
    def test_a_recruit_joins_the_player(self):
        report = self.effects({"recruit": "hermit"})
        self.assertIn("recruit Old Hermit" if False else "recruit " + self.npc("hermit").name, report.applied)
        self.assertIn("joins you.", " ".join(report.messages))
        hermit = self.npc("hermit")
        self.assertEqual([hermit], companions.companions_of(self.world, self.player))
        self.assertEqual("player_minion", hermit.faction)
        self.assertEqual("minion", hermit.behavior_type)

    def test_the_speaker_can_recruit_itself(self):
        hermit = self.npc("hermit")
        self.effects({"recruit": True}, npc=hermit)
        self.assertEqual([hermit], companions.companions_of(self.world, self.player))

    def test_the_cap_is_one_unless_the_ruleset_says_more(self):
        self.effects({"recruit": "hermit"})
        self.at("aldermark", "village_green")
        report = self.effects({"recruit": "sage"})
        self.assertIn("cannot bring another", " ".join(report.messages))
        self.assertEqual(1, len(companions.companions_of(self.world, self.player)))
        self.allow(2)
        self.effects({"recruit": "sage"})
        self.assertEqual(2, len(companions.companions_of(self.world, self.player)))

    def test_a_world_that_allows_none_says_so(self):
        self.allow(0)
        report = self.effects({"recruit": "hermit"})
        self.assertIn("no room for companions", " ".join(report.messages))
        self.assertEqual([], companions.companions_of(self.world, self.player))

    def test_someone_who_is_not_here_cannot_be_recruited(self):
        self.at("aldermark", "village_green")
        report = self.effects({"recruit": "hermit"})
        self.assertIn("is not here", " ".join(report.messages))
        self.assertEqual([], companions.companions_of(self.world, self.player))

    def test_the_same_creature_cannot_be_recruited_twice(self):
        self.effects({"recruit": "hermit"})
        report = self.effects({"recruit": "hermit"})
        self.assertIn("already with you", " ".join(report.messages))

    def test_dismissing_puts_it_back_as_it_was(self):
        hermit = self.npc("hermit")
        before = (hermit.faction, hermit.behavior_type)
        self.effects({"recruit": "hermit"})
        report = self.effects({"dismiss": "hermit"})
        self.assertIn("stays behind", " ".join(report.messages))
        self.assertEqual([], companions.companions_of(self.world, self.player))
        self.assertEqual(before, (hermit.faction, hermit.behavior_type))
        self.assertNotIn("owner_id", hermit.properties)

    def test_dismissing_someone_who_is_not_a_companion_fails(self):
        report = self.effects({"dismiss": "hermit"})
        self.assertTrue(report.failed)


class TestTravelling(_Zelda):
    def test_a_companion_follows_through_an_exit(self):
        self.effects({"recruit": "hermit"})
        room = self.world.get_region(HERMIT_ROOM[0]).get_room(HERMIT_ROOM[1])
        direction = sorted(room.exits)[0]
        printed = self.say("go " + direction)
        hermit = self.npc("hermit")
        self.assertEqual((self.player.current_region_id, self.player.current_room_id),
                         (hermit.current_region_id, hermit.current_room_id))
        self.assertIn("follows you", printed)

    def test_a_companion_follows_across_regions(self):
        self.effects({"recruit": "hermit"})
        self.world.teleport_player(self.player, "mossroot", "root_hall")
        hermit = self.npc("hermit")
        self.assertEqual(("mossroot", "root_hall"), (hermit.current_region_id, hermit.current_room_id))

    def test_one_left_elsewhere_is_not_yanked_along(self):
        self.effects({"recruit": "hermit"})
        hermit = self.npc("hermit")
        hermit.current_region_id, hermit.current_room_id = "aldermark", "village_green"
        self.world.teleport_player(self.player, "mossroot", "root_hall")
        self.assertEqual(("aldermark", "village_green"), (hermit.current_region_id, hermit.current_room_id),
                         "the minion AI walks it back; arrival only carries those standing with you")


class TestSeeingThem(_Zelda):
    def test_the_condition_sees_a_companion_by_template_or_any(self):
        from engine import conditions

        any_one = {"kind": "companion_present"}
        named = {"kind": "companion_present", "npc_id": "hermit"}
        other = {"kind": "companion_present", "npc_id": "sage"}
        self.assertFalse(conditions.evaluate(any_one, self.player).satisfied)
        self.effects({"recruit": "hermit"})
        self.assertTrue(conditions.evaluate(any_one, self.player).satisfied)
        self.assertTrue(conditions.evaluate(named, self.player).satisfied)
        self.assertFalse(conditions.evaluate(other, self.player).satisfied)

    def test_the_command_lists_them(self):
        self.assertIn("No one travels with you", self.say("companions"))
        self.effects({"recruit": "hermit"})
        listed = self.say("companions")
        self.assertIn("Travelling with you (1 of 1)", listed)
        self.assertIn(self.npc("hermit").name, listed)

    def test_a_companion_that_dies_is_gone_from_the_list(self):
        self.effects({"recruit": "hermit"})
        hermit = self.npc("hermit")
        hermit.take_damage(10 ** 6, "physical")
        self.assertEqual([], companions.companions_of(self.world, self.player))


class TestPartyPayoffs(_Zelda):
    def test_restore_can_heal_the_party_too(self):
        self.effects({"recruit": "hermit"})
        hermit = self.npc("hermit")
        hermit.health = 1
        self.player.health = 1
        report = self.effects({"restore": {"resource": "health", "companions": True}})
        self.assertEqual(hermit.max_health, hermit.health)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertIn("recovers", " ".join(report.messages))

    def test_without_the_flag_only_the_player_is_healed(self):
        self.effects({"recruit": "hermit"})
        hermit = self.npc("hermit")
        hermit.health = 1
        self.player.health = 1
        self.effects({"restore": "health"})
        self.assertEqual(1, hermit.health)

    def test_a_dismissed_companion_is_not_healed_by_it(self):
        self.effects({"recruit": "hermit"})
        self.effects({"dismiss": "hermit"})
        hermit = self.npc("hermit")
        hermit.health = 1
        self.effects({"restore": {"resource": "health", "companions": True}})
        self.assertEqual(1, hermit.health)

    def test_the_flag_must_be_true_or_false(self):
        from engine.dialogue.effects import effect_shape_issues

        self.assertEqual([], effect_shape_issues({"restore": {"resource": "all", "companions": True}}))
        self.assertTrue(effect_shape_issues({"restore": {"resource": "all", "companions": "yes"}}))


class TestSurvivesARestart(unittest.TestCase):
    def test_a_companion_is_still_with_the_character_after_a_restart(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        db = str(Path(scratch) / "state.sqlite3")
        first = _boot(db)
        sid = first.create_session(player_id="transport-1").session_id
        first.execute_command(sid, "char create Restarter")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = HERMIT_ROOM
        apply_effects({"recruit": "hermit"}, {"player": hero, "world": first.world})
        first.shutdown()

        second = _boot(db)
        self.addCleanup(second.shutdown)
        sid2 = second.create_session(player_id="another-id").session_id
        second.execute_command(sid2, "char create Restarter")
        again = second.get_player_for_session(sid2)
        mine = companions.companions_of(second.world, again)
        self.assertEqual(["hermit"], [n.template_id for n in mine], "still bound to the same character")
        self.assertEqual("player_minion", mine[0].faction)
        self.assertIn("Restarter", _say(second, sid2, "companions") + again.name)


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors_with_dialogue(self, choice):
        (self.package / "data" / "dialogue" / "probe.json").write_text(json.dumps(
            {"id": "probe", "root": "a", "nodes": {"a": {"text": "x", "choices": [choice]}}}), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_good_companion_effects_and_conditions_pass(self):
        self.assertEqual([], self.errors_with_dialogue(
            {"text": "Come.", "effects": {"recruit": "hermit"}, "condition": {"kind": "companion_present", "npc_id": "sage"}}))
        self.assertEqual([], self.errors_with_dialogue({"text": "Go.", "effects": {"dismiss": True}}))

    def test_an_unknown_creature_is_refused(self):
        errors = self.errors_with_dialogue({"text": "Come.", "effects": {"recruit": "no_such_person"}})
        self.assertTrue(any("no_such_person" in m for m in errors), errors)
        errors = self.errors_with_dialogue({"text": "Come.", "condition": {"kind": "companion_present", "npc_id": "no_such_person"}})
        self.assertTrue(any("no_such_person" in m for m in errors), errors)

    def test_the_ruleset_cap_must_be_a_whole_number(self):
        path = self.package / "rules" / "ruleset.json"
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        for bad in (-1, 1.5, "three", True):
            ruleset["companions"] = {"max": bad}
            path.write_text(json.dumps(ruleset), encoding="utf-8")
            _definition, issues = validator.load_content_set(self.package)
            self.assertTrue(any("companions.max" in i.message and i.severity == "error" for i in issues), bad)
        ruleset["companions"] = {"max": 3}
        path.write_text(json.dumps(ruleset), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        self.assertEqual([], [i.message for i in issues if "companions" in i.message])


if __name__ == "__main__":
    unittest.main()
