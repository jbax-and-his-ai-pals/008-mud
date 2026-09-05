# tests/singles/test_combat_system_full.py
"""Coverage for engine/core/combat_system.py's execute_attack(): the
non-generic-weapon miss message, and the "you have been defeated" branch
when the defeated defender is the viewer."""

import unittest
from unittest.mock import patch

from engine.core.combat_system import CombatSystem


class _Entity:
    def __init__(self, name="Thing", faction="neutral", level=1, agility=10):
        self.name = name
        self.faction = faction
        self.level = level
        self._agility = agility
        self.is_alive = True
        self.health = 10

    def has_effect(self, name):
        return False

    def get_effective_stat(self, stat_name):
        return self._agility

    def take_damage(self, amount, damage_type="physical"):
        self.health -= amount
        if self.health <= 0:
            self.is_alive = False
        return amount

    def heal(self, amount):
        self.health += amount


class TestExecuteAttackMiss(unittest.TestCase):
    def test_miss_with_named_weapon_includes_weapon_in_message(self):
        attacker = _Entity(name="Attacker")
        defender = _Entity(name="Defender")
        with patch("engine.core.combat_system.random.random", return_value=0.99):
            result = CombatSystem.execute_attack(
                attacker, defender, attack_power=5, weapon_name="item_iron_sword",
            )
        self.assertFalse(result["is_hit"])
        self.assertIn("iron sword", result["message"])
        self.assertIn("miss", result["message"])


class TestExecuteAttackDefeat(unittest.TestCase):
    def test_defeated_viewer_defender_gets_you_have_been_defeated_message(self):
        attacker = _Entity(name="Attacker")
        defender = _Entity(name="Defender")
        defender.health = 1
        result = CombatSystem.execute_attack(
            attacker, defender, attack_power=50, weapon_name="attack",
            always_hit=True, viewer=defender,
        )
        self.assertTrue(result["target_defeated"])
        self.assertIn("You have been defeated!", result["message"])


if __name__ == "__main__":
    unittest.main()
