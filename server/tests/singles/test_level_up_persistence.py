# tests/singles/test_level_up_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.config import PLAYER_LEVEL_UP_STAT_INCREASE

class TestLevelUpPersistence(GameTestBase):
    
    TEST_SAVE = "test_lvl_persist.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_stats_remain_after_load(self):
        """Verify leveled stats persist."""
        start_str = self.player.stats["strength"]
        
        # 1. Level Up
        self.player.gain_experience(self.player.runtime_state.progression.experience_to_level)
        self.assertEqual(self.player.runtime_state.progression.level, 2)
        
        expected_str = start_str + PLAYER_LEVEL_UP_STAT_INCREASE
        self.assertEqual(self.player.stats["strength"], expected_str)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Reload
        self.world.load_save_game(self.TEST_SAVE)
        loaded = self.world.player
        
        # 4. Assert
        self.assertIsNotNone(loaded)
        if loaded:
            self.assertEqual(loaded.runtime_state.progression.level, 2)
            self.assertEqual(loaded.stats["strength"], expected_str)
