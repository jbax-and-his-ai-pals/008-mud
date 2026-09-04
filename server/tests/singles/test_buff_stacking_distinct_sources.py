# tests/singles/test_buff_stacking_distinct_sources.py
import time
from tests.fixtures import GameTestBase

class TestBuffStackingDistinctSources(GameTestBase):

    def test_different_buffs_stack(self):
        """Verify two different buffs affecting the same stat accumulate."""
        base_str = self.player.stats["strength"]
        
        # Buff 1: Potion of Might
        b1 = {
            "name": "Potion Strength", "type": "stat_mod", 
            "modifiers": {"strength": 5}, "base_duration": 100.0
        }
        
        # Buff 2: Spell Bull's Strength
        b2 = {
            "name": "Spell Strength", "type": "stat_mod", 
            "modifiers": {"strength": 10}, "base_duration": 100.0
        }
        
        # Apply both
        self.player.apply_effect(b1, time.time())
        self.player.apply_effect(b2, time.time())
        
        # Check Total (Base + 5 + 10)
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 15)
        
        # Remove one
        self.player.remove_effect("Potion Strength")
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 10)