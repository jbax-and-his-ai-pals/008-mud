# tests/singles/test_level_growth.py
"""What a level brings is the content set's to say (`advancement.level_up`), not an engine constant."""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.core import level_growth
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
FF4 = STORY_FIXTURE   # a frozen copy: these are engine features, not the story
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _hero(case, level_up=None):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(FF4), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    if level_up is not None:
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"level_up": level_up} if name == "advancement" else original(name)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Cecil")
    return server.get_player_for_session(sid)


def _needed(player):
    return player.runtime_state.progression.experience_to_level - player.runtime_state.progression.experience


class TestWhatALevelBrings(unittest.TestCase):
    def test_a_set_that_says_nothing_plays_as_it_always_did(self):
        player = _hero(self)
        before = dict(player.stats)
        health = player.max_health
        player.gain_experience(_needed(player))
        for stat, value in before.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.assertEqual(value + 1, player.stats[stat], stat)
        self.assertGreater(player.max_health, health)
        self.assertEqual(({"default": 1}, level_growth.DEFAULT_HEALTH_BASE), level_growth.level_up_settings(player.world))

    def test_each_stat_grows_by_what_the_set_says_and_the_rest_by_the_default(self):
        player = _hero(self, {"stat_growth": {"default": 1, "strength": 3, "agility": 0}})
        before = dict(player.stats)
        player.gain_experience(_needed(player))
        self.assertEqual(before["strength"] + 3, player.stats["strength"])
        self.assertEqual(before["agility"], player.stats["agility"], "a stat set to 0 never grows")
        self.assertEqual(before["wisdom"] + 1, player.stats["wisdom"])

    def test_the_default_can_be_changed_too(self):
        player = _hero(self, {"stat_growth": {"default": 2}})
        before = dict(player.stats)
        player.gain_experience(_needed(player))
        self.assertEqual(before["dexterity"] + 2, player.stats["dexterity"])

    def test_the_flat_part_of_a_levels_health_is_the_sets_to_choose(self):
        small = _hero(self, {"health_base": 0})
        large = _hero(self, {"health_base": 20})
        small_before, large_before = small.max_health, large.max_health
        small.gain_experience(_needed(small))
        large.gain_experience(_needed(large))
        self.assertEqual(20, (large.max_health - large_before) - (small.max_health - small_before))

    def test_the_report_shows_only_what_grew_and_sums_several_levels(self):
        player = _hero(self, {"stat_growth": {"default": 0, "strength": 2}})
        _leveled, report = player.gain_experience(5000)
        gained = player.runtime_state.progression.level - 1
        self.assertGreaterEqual(gained, 2)
        text = _MARKUP.sub("", report)
        self.assertIn("Strength: ", text)
        self.assertIn("(+%d)" % (2 * gained), text)
        self.assertNotIn("Wisdom", text, "a stat that did not grow is not listed")

    def test_nonsense_falls_back_to_the_defaults(self):
        growth, health = level_growth.level_up_settings(_hero(self, {"stat_growth": {"strength": "lots", "agility": -1}, "health_base": "big"}).world)
        self.assertEqual({"default": 1}, growth)
        self.assertEqual(level_growth.DEFAULT_HEALTH_BASE, health)


class TestTheValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "story_fixture"
        shutil.copytree(FF4, self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors_with(self, level_up):
        from engine.server import content_set as validator

        path = self.package / "rules" / "ruleset.json"
        rules = json.loads(path.read_text(encoding="utf-8"))
        rules.setdefault("advancement", {})["level_up"] = level_up
        path.write_text(json.dumps(rules, indent=2), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_good_settings_pass(self):
        for good in ({}, {"health_base": 0}, {"stat_growth": {"default": 2, "strength": 0.5}}, {"stat_growth": {}, "health_base": 12}):
            self.assertEqual([], self.errors_with(good), good)

    def test_bad_settings_are_refused_and_say_what_would_work(self):
        self.assertTrue(any("must be an object" in m for m in self.errors_with("lots")))
        self.assertTrue(any("is not read" in m and "stat_growth" in m for m in self.errors_with({"growth": 1})))
        self.assertTrue(any("stat_growth must be an object" in m for m in self.errors_with({"stat_growth": 3})))
        self.assertTrue(any("stat_growth.strength" in m for m in self.errors_with({"stat_growth": {"strength": -1}})))
        self.assertTrue(any("stat_growth.strength" in m for m in self.errors_with({"stat_growth": {"strength": "lots"}})))
        self.assertTrue(any("health_base" in m for m in self.errors_with({"health_base": -5})))
        self.assertTrue(any("health_base" in m for m in self.errors_with({"health_base": True})))


if __name__ == "__main__":
    unittest.main()
