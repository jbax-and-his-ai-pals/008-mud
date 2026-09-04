# tests/singles/test_weather_persistence.py
import os
from tests.fixtures import GameTestBase

class TestWeatherPersistence(GameTestBase):
    
    TEST_SAVE = "test_weather.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_weather_state_saves(self):
        """Verify weather conditions persist."""
        wm = self.game.weather_manager
        
        # 1. Set specific weather
        wm.current_weather = "storm"
        wm.current_intensity = "severe"
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Reset
        wm.current_weather = "clear"
        wm.current_intensity = "mild"
        
        # 4. Load
        success, loaded_time, loaded_weather = self.world.load_save_game(self.TEST_SAVE)
        self.assertTrue(success)
        
        # FIX: Manually apply loaded state (normally done by 'load' command)
        if loaded_weather:
            wm.apply_loaded_weather_state(loaded_weather)
        
        # 5. Assert
        self.assertEqual(wm.current_weather, "storm")
        self.assertEqual(wm.current_intensity, "severe")