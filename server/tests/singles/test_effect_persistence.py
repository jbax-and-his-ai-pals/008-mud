# tests/singles/test_effect_persistence.py
import os
import time
from tests.fixtures import GameTestBase

class TestEffectPersistence(GameTestBase):
    
    TEST_SAVE = "test_effects_save.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_buff_save_load(self):
        """Verify active buffs persist through save/load."""
        # 1. Apply a long-duration buff
        buff = {
            "name": "Save Persistence Test",
            "type": "stat_mod",
            "base_duration": 100.0,
            "modifiers": {"strength": 50}
        }
        self.player.apply_effect(buff, time.time())
        
        # Verify applied
        self.assertTrue(self.player.has_effect("Save Persistence Test"))
        self.assertEqual(self.player.get_effective_stat("strength"), self.player.stats["strength"] + 50)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Wipe Player State
        self.player.active_effects = []
        self.player.stat_modifiers = {}
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded_player = self.world.player
        
        # 5. Assert
        self.assertIsNotNone(loaded_player)
        if loaded_player:
            self.assertTrue(loaded_player.has_effect("Save Persistence Test"), "Buff should exist after load.")
            # Check duration is roughly correct (allowing for small tick deltas)
            effect = next(e for e in loaded_player.active_effects if e["name"] == "Save Persistence Test")
            self.assertGreater(effect["duration_remaining"], 90.0)
            
            # Check Stat Calculation recalculated correctly
            self.assertEqual(loaded_player.get_effective_stat("strength"), loaded_player.stats["strength"] + 50)