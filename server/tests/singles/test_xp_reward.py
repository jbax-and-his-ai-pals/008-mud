# tests/singles/test_xp_reward.py
"""`properties.xp_reward`: a creature worth a fixed amount of experience, whoever kills it."""

import unittest

from engine.core import kill_credit

from tests.singles.test_encounters import _game


class _Victim:
    def __init__(self, properties, level=1, max_health=10):
        self.properties = properties
        self.level = level
        self.max_health = max_health


class TestFixedExperience(unittest.TestCase):
    def test_a_fixed_reward_is_what_is_paid_whatever_the_levels(self):
        _server, player = _game(self)
        self.assertEqual(45, kill_credit.experience_for(player, _Victim({"xp_reward": 45}, level=99, max_health=9999), 1.0))

    def test_a_share_of_it_is_a_share(self):
        _server, player = _game(self)
        self.assertEqual(20, kill_credit.experience_for(player, _Victim({"xp_reward": 40}), 0.5))

    def test_without_it_the_engines_formula_is_used(self):
        _server, player = _game(self)
        formula = kill_credit.experience_for(player, _Victim({}, level=3, max_health=30), 1.0)
        self.assertGreater(formula, 0)
        self.assertNotEqual(45, formula)

    def test_nonsense_falls_back_to_the_formula(self):
        _server, player = _game(self)
        for junk in (True, "many", -3):
            self.assertGreater(kill_credit.experience_for(player, _Victim({"xp_reward": junk}), 1.0), 0)


class TestTheValidator(unittest.TestCase):
    def test_a_bad_reward_is_refused(self):
        from engine.server.content_set.npcs import _npc_property_errors

        for bad in (-1, 2.5, True, "many"):
            errors = _npc_property_errors({"xp_reward": bad}, "npc 'x'", set())
            self.assertTrue([e for e in errors if "xp_reward" in e], bad)
        self.assertEqual([], [e for e in _npc_property_errors({"xp_reward": 45}, "npc 'x'", set()) if "xp_reward" in e])


if __name__ == "__main__":
    unittest.main()
