# tests/singles/test_mana_regen_modifiers.py
import time
from tests.fixtures import GameTestBase
from engine.config import PLAYER_REGEN_TICK_INTERVAL

class TestManaRegenModifiers(GameTestBase):

    def test_wisdom_impact_on_regen(self):
        """Verify higher wisdom results in more mana regenerated per tick."""
        self.player.runtime_state.magic.max_mana = 100
        
        # 1. Low Wisdom (10)
        self.player.stats["wisdom"] = 10
        self.player.runtime_state.magic.mana = 0
        
        # Force one tick
        # Formula: Base(1.0) * (1 + Wis/20) * Interval
        # 1.0 * (1 + 0.5) * 1.0 = 1.5 -> int(1)
        
        future_time = time.time() + PLAYER_REGEN_TICK_INTERVAL + 0.1
        self.player.update(future_time, 0.1)
        
        regen_low = self.player.runtime_state.magic.mana
        
        # 2. High Wisdom (40)
        self.player.stats["wisdom"] = 40
        self.player.runtime_state.magic.mana = 0
        
        # Reset timer
        self.player.last_mana_regen_time = time.time()
        future_time = time.time() + PLAYER_REGEN_TICK_INTERVAL + 0.1
        
        self.player.update(future_time, 0.1)
        regen_high = self.player.runtime_state.magic.mana
        
        # 3. Assert
        self.assertGreater(regen_high, regen_low, "High wisdom should regenerate more mana.")
