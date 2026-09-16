# engine/core/weather_manager.py
"""
Core system for managing dynamic in-game weather.
"""
import random
from typing import Any, Dict

from engine.config import (WEATHER_INTENSITY_WEIGHTS, WEATHER_PERSISTENCE_CHANCE,
                         WEATHER_TRANSITION_CHANGE_CHANCE)


DEFAULT_WEATHER_CHANCES = {
    "spring": {"clear": 0.4, "cloudy": 0.3, "rain": 0.3, "storm": 0.1},
    "summer": {"clear": 0.6, "cloudy": 0.2, "rain": 0.1, "storm": 0.1},
    "fall": {"clear": 0.3, "cloudy": 0.4, "rain": 0.2, "storm": 0.1},
    "winter": {"clear": 0.5, "cloudy": 0.3, "snow": 0.2}
}


class WeatherManager:
    def __init__(self, world=None):
        # Content sets override the season->weather-type probability table
        # via a "weather.chances" ruleset section; this is a reasonable,
        # theme-neutral real-world default for content sets that don't.
        chances = None
        if world is not None:
            weather_rules = world.ruleset_section("weather")
            raw = weather_rules.get("chances")
            if isinstance(raw, dict) and raw:
                chances = raw
            raw_profiles = weather_rules.get("profiles", {})
            self.weather_profiles = raw_profiles if isinstance(raw_profiles, dict) else {}
        else:
            self.weather_profiles = {}
        self.weather_chances = chances or DEFAULT_WEATHER_CHANCES
        self.current_weather = "clear"
        self.current_intensity = "mild"

    def effective_weather(self, region=None, room=None) -> str:
        """Return the weather a player experiences in this specific place.

        Rooms may author an immutable local climate (a glacial cave, for
        example). Otherwise a region selects a content-owned climate profile
        that can translate global weather into its local expression: rain on
        an alpine pass becomes snow, while a clear day over marshland becomes
        mist. Profiles are descriptive values, not an engine-maintained biome
        taxonomy.
        """
        if room is not None:
            local = room.get_property("weather")
            if isinstance(local, str) and local.strip():
                return local.strip()
        profile_id = ""
        if region is not None:
            profile_id = str(region.get_property("weather_profile", "") or "").strip()
        profile = self.weather_profiles.get(profile_id, {})
        mapping = profile.get("map", {}) if isinstance(profile, dict) else {}
        mapped = mapping.get(self.current_weather) if isinstance(mapping, dict) else None
        return str(mapped).strip() if isinstance(mapped, str) and mapped.strip() else self.current_weather

    def travel_note(self, region=None, room=None) -> str:
        """Return a content-authored travel advisory for exposed local weather."""
        if room is None or not room.get_property("outdoors", True):
            return ""
        profile_id = str(region.get_property("weather_profile", "") or "") if region is not None else ""
        profile = self.weather_profiles.get(profile_id, {})
        notes = profile.get("travel_notes", {}) if isinstance(profile, dict) else {}
        note = notes.get(self.effective_weather(region, room)) if isinstance(notes, dict) else None
        return str(note).strip() if isinstance(note, str) else ""

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
