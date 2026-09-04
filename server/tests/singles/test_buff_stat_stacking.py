# tests/singles/test_buff_stat_stacking.py
import time
from tests.fixtures import GameTestBase

class TestBuffStatStacking(GameTestBase):

    def test_buff_stacking_logic(self):
        """Verify applying different buffs stacks stats, same buff refreshes."""
        base_str = self.player.stats["strength"]
        
        # Buff A
        buff_a = {"name": "Might", "type": "stat_mod", "modifiers": {"strength": 5}}
        # Buff B
        buff_b = {"name": "Rage", "type": "stat_mod", "modifiers": {"strength": 10}}
        
        # 1. Apply A
        self.player.apply_effect(buff_a, time.time())
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 5)
        
        # 2. Apply B
        self.player.apply_effect(buff_b, time.time())
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 15)
        
        # 3. Re-apply A (Refresh)
        # Should not add another +5
        self.player.apply_effect(buff_a, time.time())
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 15)
        
        # 4. Check active effects list size
        names = [e["name"] for e in self.player.active_effects]
        self.assertEqual(names.count("Might"), 1)
        self.assertEqual(names.count("Rage"), 1)