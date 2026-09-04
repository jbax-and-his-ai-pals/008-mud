# tests/singles/test_stat_mod_stacking.py
import time
from tests.fixtures import GameTestBase

class TestStatModStacking(GameTestBase):

    def test_identical_buff_refresh(self):
        """Verify applying the same buff name refreshes duration instead of stacking stats."""
        base_agi = self.player.stats["agility"]
        
        buff = {
            "name": "Haste",
            "type": "stat_mod",
            "base_duration": 10.0,
            "modifiers": {"agility": 5}
        }
        
        # 1. Apply first time
        self.player.apply_effect(buff, time.time())
        self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 5)
        
        # 2. Apply second time
        self.player.apply_effect(buff, time.time())
        
        # 3. Assert stats didn't double (still +5, not +10)
        self.assertEqual(self.player.get_effective_stat("agility"), base_agi + 5, "Buffs with same name should not stack values.")
        
        # 4. Verify only one instance exists in active_effects
        haste_effects = [e for e in self.player.active_effects if e["name"] == "Haste"]
        self.assertEqual(len(haste_effects), 1)

    def test_different_buff_stacking(self):
        """Verify different buffs correctly sum their modifiers."""
        base_str = self.player.stats["strength"]
        
        buff1 = {"name": "Might", "type": "stat_mod", "modifiers": {"strength": 2}}
        buff2 = {"name": "Fury", "type": "stat_mod", "modifiers": {"strength": 3}}
        
        self.player.apply_effect(buff1, time.time())
        self.player.apply_effect(buff2, time.time())
        
        self.assertEqual(self.player.get_effective_stat("strength"), base_str + 5)