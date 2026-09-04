# tests/singles/test_combat.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
import time

class TestCombat(GameTestBase):
    def setUp(self):
        super().setUp()
        # CRITICAL: Zero out base stats to ensure combat math is deterministic for tests.
        # Default stats usually have defense: 3, magic_resist: 2.
        self.player.stats["defense"] = 0
        self.player.stats["magic_resist"] = 0
        self.player.stats["resistances"] = {} # Clear any innate resistances
        
        # Reset health/mana
        self.player.max_health = 100
        self.player.health = 100
        self.player.max_mana = 50
        self.player.mana = 50

    def test_physical_damage_math(self):
        """Verify raw physical damage and defense reduction."""
        # 1. Raw damage (No defense)
        # 10 damage -> 100 - 10 = 90
        damage_taken = self.player.take_damage(10, "physical")
        self.assertEqual(damage_taken, 10)
        self.assertEqual(self.player.health, 90)

        # 2. Defense reduction
        self.player.stat_modifiers["defense"] = 5
        # 10 damage - 5 defense = 5 taken
        damage_taken = self.player.take_damage(10, "physical")
        self.assertEqual(damage_taken, 5)
        self.assertEqual(self.player.health, 85)

    def test_magic_resistance(self):
        """Verify elemental resistance reduces damage correctly."""
        # Setup: 50% Fire Resistance
        # Note: Stats are zeroed in setUp, so no flat reduction applies first
        self.player.stats["resistances"] = {"fire": 50}
        
        # Act: Take 20 Fire Damage
        # Calc: 20 * (1 - 0.50) = 10
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
            "last_tick_time": time.time() - 2.0 # Force ready to tick
        }
        self.player.active_effects.append(effect)
        
        # Act: Process Effects (simulate 1.0s passing)
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