# tests/singles/test_status_effects.py
import time
from tests.fixtures import GameTestBase

class TestStatusEffects(GameTestBase):
    
    def test_stat_buff_application_and_expiration(self):
        """Verify stat modifiers apply to effective stats and revert after duration."""
        base_str = self.player.stats["strength"]
        
        # 1. Apply Buff (+5 Strength for 10 seconds)
        buff_effect = {
            "name": "Bull's Strength",
            "type": "stat_mod",
            "base_duration": 10.0,
            "modifiers": {"strength": 5}
        }
        
        success, msg = self.player.apply_effect(buff_effect, time.time())
        self.assertTrue(success)
        
        # 2. Verify Stat Increase
        effective_str = self.player.get_effective_stat("strength")
        self.assertEqual(effective_str, base_str + 5, "Strength should increase by 5.")
        
        # 3. Simulate Time Passing (5 seconds - Buff active)
        self.player.update(time.time() + 5.0, 5.0)
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 5, "Buff should still be active.")
        
        # 4. Simulate Time Passing (6 seconds more - Buff expired)
        self.player.update(time.time() + 11.0, 6.0)
        self.assertEqual(self.player.get_effective_stat("strength"), base_str, "Buff should have expired.")
        self.assertFalse(self.player.has_effect("Bull's Strength"))

    def test_dot_application(self):
        """Verify Damage Over Time effects tick and reduce health."""
        # FIX: Zero out resistance to ensure deterministic damage
        self.player.stats["magic_resist"] = 0
        self.player.stat_modifiers = {}
        
        start_hp = self.player.health
        damage_per_tick = 5
        
        # 1. Apply Poison
        dot_effect = {
            "name": "Weak Poison",
            "type": "dot",
            "base_duration": 10.0,
            "damage_per_tick": damage_per_tick,
            "tick_interval": 1.0,
            "damage_type": "poison"
        }
        self.player.apply_effect(dot_effect, time.time())
        
        # 2. Process Tick (1 second later)
        # We manually trigger process_active_effects to capture the output messages
        messages = self.player.process_active_effects(time.time() + 1.1, 1.1)
        
        # 3. Verify Damage
        self.assertLess(self.player.health, start_hp)
        self.assertEqual(self.player.health, start_hp - damage_per_tick) 
        self.assertTrue(any("poison damage" in m.lower() or "weak poison" in m.lower() for m in messages))