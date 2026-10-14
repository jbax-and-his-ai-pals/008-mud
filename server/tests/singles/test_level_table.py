# tests/singles/test_level_table.py
"""`advancement.level_table`: a set says what each level *is*, not what it adds."""

import re
import unittest

from engine.core import level_table
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
TABLE = [
    {"xp": 7, "stats": {"strength": 4, "agility": 4}, "max_health": 15, "max_mana": 0},
    {"xp": 16, "stats": {"strength": 5, "agility": 4}, "max_health": 22, "max_mana": 0},
    {"xp": 24, "stats": {"strength": 7, "agility": 6}, "max_health": 24, "max_mana": 5},
    {"stats": {"strength": 7, "agility": 8}, "max_health": 31, "max_mana": 16},
]


def _hero(case, table=None):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    if table is not None:
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"level_table": table} if name == "advancement" else original(name)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    return server.get_player_for_session(sid), server


class TestLevelTable(unittest.TestCase):
    def test_a_set_with_no_table_has_none(self):
        player, _server = _hero(self)
        self.assertEqual([], level_table.table_of(player.world))
        self.assertIsNone(level_table.cost_to_next(player.world, 1))

    def test_a_new_character_is_level_one_of_the_table(self):
        player, _server = _hero(self, TABLE)
        self.assertEqual(15, player.max_health)
        self.assertEqual(15, player.health)
        self.assertEqual(4, player.stats["strength"])
        self.assertEqual(4, player.stats["agility"])
        self.assertEqual(0, player.runtime_state.magic.max_mana)
        self.assertEqual(7, player.runtime_state.progression.experience_to_level)

    def test_each_level_is_what_the_row_says_and_costs_what_the_row_says(self):
        player, _server = _hero(self, TABLE)
        player.gain_experience(7)
        self.assertEqual(2, player.runtime_state.progression.level)
        self.assertEqual((5, 4, 22), (player.stats["strength"], player.stats["agility"], player.max_health))
        self.assertEqual(16, player.runtime_state.progression.experience_to_level)
        player.gain_experience(16 + 24)
        self.assertEqual(4, player.runtime_state.progression.level)
        self.assertEqual((7, 8, 31, 16), (player.stats["strength"], player.stats["agility"], player.max_health, player.runtime_state.magic.max_mana))

    def test_the_last_row_is_the_cap(self):
        player, _server = _hero(self, TABLE)
        player.gain_experience(10 ** 6)
        self.assertEqual(4, player.runtime_state.progression.level)
        player.gain_experience(10 ** 6)
        self.assertEqual(4, player.runtime_state.progression.level)

    def test_recalculating_health_keeps_the_table_not_the_formula(self):
        player, _server = _hero(self, TABLE)
        player.recalculate_max_health()
        self.assertEqual(15, player.max_health)

    def test_health_and_pool_rise_by_what_the_level_gave(self):
        player, _server = _hero(self, TABLE)
        player.health = 5
        player.gain_experience(7)
        self.assertEqual(5 + (22 - 15), player.health)


class TestLevelTableValidation(unittest.TestCase):
    def _issues(self, table):
        from engine.server.content_set.advancement import _validate_level_table
        from pathlib import Path
        issues = []
        _validate_level_table(table, {}, issues, Path("ruleset.json"))
        return [i for i in issues if i.severity == "error"]

    def test_a_good_table_is_accepted(self):
        self.assertEqual([], self._issues(TABLE))

    def test_each_mistake_is_named(self):
        self.assertTrue(self._issues([]))
        self.assertTrue(self._issues({"xp": 1}))
        self.assertTrue(self._issues([{"stats": {"strength": 1}}, {"max_health": 5}]), "a row that is not last needs xp")
        self.assertTrue(self._issues([{"xp": 0, "max_health": 5}, {"max_health": 6}]))
        self.assertTrue(self._issues([{"xp": 5, "speed": 1}, {"max_health": 6}]), "unknown key")
        self.assertTrue(self._issues([{"xp": 5, "stats": {"strength": "x"}}, {"max_health": 6}]))
        self.assertTrue(self._issues([{"xp": 5, "max_health": 0}, {"max_health": 6}]))


if __name__ == "__main__":
    unittest.main()
