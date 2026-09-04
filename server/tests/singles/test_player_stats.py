# tests/singles/test_player_stats.py
import time
from tests.fixtures import GameTestBase
from engine.config import PLAYER_REGEN_TICK_INTERVAL

class TestPlayerStats(GameTestBase):
    
    def test_health_regeneration(self):
        """Verify health regenerates over time."""
        self.player.max_health = 100
        self.player.health = 50
        
        # Simulate time passing beyond the tick interval
        current_time = time.time()
        future_time = current_time + PLAYER_REGEN_TICK_INTERVAL + 0.1
        
        # Act
        self.player.update(future_time, 0.1)
        
        # Assert
        self.assertGreater(self.player.health, 50, "Health should have regenerated")
        self.assertLessEqual(self.player.health, 100, "Health should not exceed max")

    def test_mana_regeneration(self):
        """Verify mana regenerates over time based on Wisdom."""
        self.player.runtime_state.magic.max_mana = 50
        self.player.runtime_state.magic.mana = 10
        self.player.stats["wisdom"] = 20 # High wisdom for noticeable regen
        
        current_time = time.time()
        future_time = current_time + PLAYER_REGEN_TICK_INTERVAL + 0.1
        
        # Act
        self.player.update(future_time, 0.1)
        
        # Assert
        self.assertGreater(self.player.runtime_state.magic.mana, 10, "Mana should have regenerated")

    def test_xp_rollover(self):
        """Verify XP rolls over after leveling up."""
        self.player.runtime_state.progression.level = 1
        self.player.runtime_state.progression.experience = 0
        self.player.runtime_state.progression.experience_to_level = 100
        
        # Act: Give 150 XP (Enough for level 2 + 50 overflow)
        leveled, msg = self.player.gain_experience(150)
        
        # Assert
        self.assertTrue(leveled)
        self.assertEqual(self.player.runtime_state.progression.level, 2)
        # 150 - 100 cost = 50 remaining
        self.assertEqual(self.player.runtime_state.progression.experience, 50)

    def test_stat_caps(self):
        """Verify stats cannot be healed beyond maximum."""
        self.player.max_health = 100
        self.player.health = 90
        
        # Act: Heal for 50
        self.player.heal(50)
        
        # Assert
        self.assertEqual(self.player.health, 100, "Health should cap at max")
