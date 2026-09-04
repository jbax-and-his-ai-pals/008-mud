# tests/singles/test_combat_extended.py
from tests.fixtures import GameTestBase
import time

class TestCombatExtended(GameTestBase):
    def setUp(self):
        super().setUp()
        # CRITICAL FIX: Zero out base stats to ensure deterministic combat math.
        # Default stats: defense=3, magic_resist=2. These mess up exact assertions.
        self.player.stats["defense"] = 0
        self.player.stats["magic_resist"] = 0
        self.player.stats["resistances"] = {} 
        self.player.stat_modifiers = {}
        
        self.player.max_health = 100
        self.player.health = 100

    def test_physical_damage_math(self):
        """Verify raw physical damage and defense reduction."""
        # 1. Raw damage (No defense)
        damage_taken = self.player.take_damage(10, "physical")
        self.assertEqual(damage_taken, 10)
        self.assertEqual(self.player.health, 90)

        # 2. Defense reduction
        self.player.stat_modifiers["defense"] = 5
        damage_taken = self.player.take_damage(10, "physical")
        self.assertEqual(damage_taken, 5)
        self.assertEqual(self.player.health, 85)

    def test_magic_resistance(self):
        """Verify elemental resistance reduces damage."""
        # Setup: 50% Fire Resistance
        self.player.stats["resistances"] = {"fire": 50}
        
        # Act: Take 20 Fire Damage
        # Calc: 20 * (1 - 0.50) = 10. (Magic Resist is 0 from setUp)
        damage_taken = self.player.take_damage(20, "fire")
        
        # Assert
        self.assertEqual(damage_taken, 10)
        self.assertEqual(self.player.health, 90)

    def test_dot_tick(self):
        """Verify Damage over Time reduces health."""
        # Setup DoT
        effect = {
            "type": "dot",
            "name": "Test Poison",
            "damage_per_tick": 5,
            "tick_interval": 1.0,
            "damage_type": "poison", # magic_resist is 0 from setUp
            "last_tick_time": time.time() - 2.0 # Force ready
        }
        self.player.active_effects.append(effect)
        
        # Act: Process Effects
        self.player.process_active_effects(time.time(), 1.0)
        
        # Assert
        # 100 - 5 = 95
        self.assertEqual(self.player.health, 95)

    def test_stat_buff_application(self):
        """Verify stat modifier effects apply and expire."""
        base_str = self.player.get_effective_stat("strength")
        
        # Apply Buff (+10 Str)
        buff = {
            "type": "stat_mod",
            "name": "Giant Strength",
            "base_duration": 10.0,
            "modifiers": {"strength": 10}
        }
        self.player.apply_effect(buff, time.time())
        
        # Check Stat
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 10)
        
        # Expire Buff
        self.player.process_active_effects(time.time() + 11.0, 11.0)
        
        # Check Revert
        self.assertEqual(self.player.get_effective_stat("strength"), base_str)