# engine/core/weather_manager.py
"""
Core system for managing dynamic in-game weather.
"""
import random
from typing import Any, Dict

from engine.config import (WEATHER_INTENSITY_WEIGHTS, WEATHER_PERSISTENCE_CHANCE,
                         WEATHER_TRANSITION_CHANGE_CHANCE)


class WeatherManager:
    def __init__(self):
        # Default weather chances, can be customized or loaded
        self.weather_chances = {
            "spring": {"clear": 0.4, "cloudy": 0.3, "rain": 0.3, "storm": 0.1},
            "summer": {"clear": 0.6, "cloudy": 0.2, "rain": 0.1, "storm": 0.1},
            "fall": {"clear": 0.3, "cloudy": 0.4, "rain": 0.2, "storm": 0.1},
            "winter": {"clear": 0.5, "cloudy": 0.3, "snow": 0.2}
        }
        self.current_weather = "clear"
        self.current_intensity = "mild"

    def update_on_time_period_change(self, season: str):
        """Updates the weather, with a higher chance of change at dawn/dusk."""
        if random.random() < WEATHER_TRANSITION_CHANGE_CHANCE:
            self._update_weather(season)

    def _update_weather(self, season: str):
        """Calculates a new weather state based on season probabilities."""
        season_chances = self.weather_chances.get(season, self.weather_chances["summer"])

        if random.random() < WEATHER_PERSISTENCE_CHANCE and self.current_weather in season_chances:
            self.current_intensity = self._get_random_intensity()
            return

        weather_types = list(season_chances.keys())
        weights = list(season_chances.values())
        
        try:
            self.current_weather = random.choices(weather_types, weights=weights, k=1)[0]
            self.current_intensity = self._get_random_intensity()
        except Exception as e:
            print(f"Error updating weather: {e}")
            self.current_weather = "clear"
            self.current_intensity = "mild"

    def _get_random_intensity(self) -> str:
        """Returns a random weather intensity based on predefined weights."""
        intensities = ["mild", "moderate", "strong", "severe"]
        return random.choices(intensities, weights=WEATHER_INTENSITY_WEIGHTS, k=1)[0]

    def get_weather_state_for_save(self) -> Dict[str, str]:
        """Gets the current weather state for saving."""
        return {
            "current_weather": self.current_weather,
            "current_intensity": self.current_intensity
        }

    def apply_loaded_weather_state(self, weather_data: Dict[str, Any]):
        """Applies a loaded weather state."""
        if weather_data and isinstance(weather_data, dict):
            self.current_weather = weather_data.get("current_weather", "clear")
            self.current_intensity = weather_data.get("current_intensity", "mild")