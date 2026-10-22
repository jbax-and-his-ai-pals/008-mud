# tests/singles/test_player_level_counts.py
"""`ruleset.combat.player_level_counts`: the player's own level in the level-difference modifiers on a blow."""

import unittest

from engine.core.combat_system import CombatSystem

from tests.singles.test_encounters import _game


def _foe(server, level):
    server.world.remove_npcs("probe_foe")
    foe, _status = server.world.spawn_npc(next(iter(server.world.npc_templates)), next(iter(server.world.regions)), next(iter(next(iter(server.world.regions.values())).rooms)), "probe_foe")
    foe.level = level
    foe.faction = "hostile"
    return foe


def _average_blow(attacker, defender):
    return sum(CombatSystem.calculate_physical_damage(attacker, defender, 20) for _ in range(300)) / 300.0


class TestPlayerLevelCounts(unittest.TestCase):
    def _hero(self, counts):
        server, player = _game(self)
        if counts:
            original = server.world.ruleset_section
            server.world.ruleset_section = lambda name: {"player_level_counts": True} if name == "combat" else original(name)
        while player.runtime_state.progression.level < 12:
            player.gain_experience(player.runtime_state.progression.experience_to_level)
        return server, player

    def test_by_default_a_player_has_no_level_and_is_read_as_level_one(self):
        server, player = self._hero(False)
        self.assertFalse(hasattr(player, "level"))
        foe = _foe(server, 12)
        self.assertLess(_average_blow(player, foe), 20 * 0.7, "a twelfth-level creature is purple to a hero who reads as level 1")

    def test_when_it_counts_a_twelfth_level_hero_meets_a_twelfth_level_creature_evenly(self):
        server, player = self._hero(True)
        self.assertEqual(12, player.level)
        foe = _foe(server, 12)
        self.assertAlmostEqual(20, _average_blow(player, foe), delta=1.5)
        self.assertAlmostEqual(20, _average_blow(foe, player), delta=1.5)


if __name__ == "__main__":
    unittest.main()
