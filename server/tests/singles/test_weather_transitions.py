# tests/singles/test_weather_transitions.py
from unittest.mock import patch
from tests.fixtures import GameTestBase

class TestWeatherTransitions(GameTestBase):

    def test_season_influence(self):
        """Verify winter has high chance of snow/clear, summer has rain/clear."""
        wm = self.game.weather_manager
        
        # 1. Force Winter
        # Patch random.random to 1.0 to bypass persistence check (force change)
        # Patch random.choices to return specific weather for verification
        with patch('random.random', return_value=1.0):
            with patch('random.choices', return_value=["snow"]):
                wm._update_weather("winter")
                
        self.assertEqual(wm.current_weather, "snow")
        
        # 2. Force Summer
        with patch('random.random', return_value=1.0):
            with patch('random.choices', return_value=["rain"]):
                wm._update_weather("summer")
            
        self.assertEqual(wm.current_weather, "rain")

    def test_intensity_change(self):
        """Verify intensity updates even if weather type persists."""
        wm = self.game.weather_manager
        wm.current_weather = "rain"
        wm.current_intensity = "mild"
        
        # Force persistence (random 0.0 < 0.3 persistence chance)
        # Then force intensity choice to "severe"
        with patch('random.random', return_value=0.0): 
            with patch('random.choices', return_value=["severe"]):
                wm._update_weather("spring")
                
        self.assertEqual(wm.current_weather, "rain") # Unchanged
        self.assertEqual(wm.current_intensity, "severe") # Changed