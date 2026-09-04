# tests/singles/test_dot_stacking_logic.py
import time
from tests.fixtures import GameTestBase

class TestDoTStackingLogic(GameTestBase):

    def test_refresh_duration(self):
        """Verify applying the same DoT refreshes duration rather than stacking instances."""
        target = self.player # Self-test
        
        dot = {
            "type": "dot", "name": "Poison", 
            "base_duration": 10.0, "damage_per_tick": 5
        }
        
        # 1. Apply First Time
        self.player.apply_effect(dot, time.time())
        self.assertEqual(len(self.player.active_effects), 1)
        
        # 2. Advance time slightly (duration decreases)
        self.player.active_effects[0]["duration_remaining"] = 5.0
        
        # 3. Apply Second Time
        self.player.apply_effect(dot, time.time())
        
        # 4. Assert
        # Should still be 1 effect
        self.assertEqual(len(self.player.active_effects), 1)
        # Duration should be reset to base (10.0)
        self.assertEqual(self.player.active_effects[0]["duration_remaining"], 10.0)