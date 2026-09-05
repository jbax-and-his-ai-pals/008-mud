# tests/singles/test_weather_manager_full.py
"""Coverage for engine/core/weather_manager.py: update_on_time_period_
change's roll gate, _update_weather's persistence-keeps-current-weather
path (including when the current weather isn't valid for the new season),
unknown-season fallback, the random.choices exception fallback,
_get_random_intensity, get_weather_state_for_save, and
apply_loaded_weather_state's valid/invalid-input branches."""

import unittest
from unittest.mock import patch

from engine.core.weather_manager import WeatherManager


class TestUpdateOnTimePeriodChange(unittest.TestCase):
    def test_roll_below_threshold_triggers_update(self):
        manager = WeatherManager()
        with patch("engine.core.weather_manager.random.random", return_value=0.0):
            with patch.object(manager, "_update_weather") as mock_update:
                manager.update_on_time_period_change("summer")
        mock_update.assert_called_once_with("summer")

    def test_roll_above_threshold_skips_update(self):
        manager = WeatherManager()
        with patch("engine.core.weather_manager.random.random", return_value=1.0):
            with patch.object(manager, "_update_weather") as mock_update:
                manager.update_on_time_period_change("summer")
        mock_update.assert_not_called()


class TestUpdateWeather(unittest.TestCase):
    def test_persistence_keeps_current_weather_and_rerolls_intensity(self):
        manager = WeatherManager()
        manager.current_weather = "rain"  # valid for "spring"
        with patch("engine.core.weather_manager.random.random", return_value=0.0):
            manager._update_weather("spring")
        self.assertEqual(manager.current_weather, "rain")

    def test_persistence_skipped_when_current_weather_invalid_for_season(self):
        manager = WeatherManager()
        manager.current_weather = "snow"  # not a valid key under "summer"
        with patch("engine.core.weather_manager.random.random", return_value=0.0):
            manager._update_weather("summer")
        self.assertIn(manager.current_weather, manager.weather_chances["summer"])

    def test_unknown_season_falls_back_to_summer_chances(self):
        manager = WeatherManager()
        with patch("engine.core.weather_manager.random.random", return_value=1.0):
            manager._update_weather("totally_bogus_season")
        self.assertIn(manager.current_weather, manager.weather_chances["summer"])

    def test_exception_during_reroll_falls_back_to_clear_mild(self):
        manager = WeatherManager()
        with patch("engine.core.weather_manager.random.random", return_value=1.0):
            with patch("engine.core.weather_manager.random.choices", side_effect=RuntimeError("boom")):
                manager._update_weather("summer")
        self.assertEqual(manager.current_weather, "clear")
        self.assertEqual(manager.current_intensity, "mild")


class TestGetRandomIntensity(unittest.TestCase):
    def test_returns_one_of_the_expected_intensities(self):
        manager = WeatherManager()
        result = manager._get_random_intensity()
        self.assertIn(result, ["mild", "moderate", "strong", "severe"])


class TestSaveAndLoadState(unittest.TestCase):
    def test_get_weather_state_for_save(self):
        manager = WeatherManager()
        manager.current_weather = "storm"
        manager.current_intensity = "severe"
        state = manager.get_weather_state_for_save()
        self.assertEqual(state, {"current_weather": "storm", "current_intensity": "severe"})

    def test_apply_loaded_weather_state_with_valid_dict(self):
        manager = WeatherManager()
        manager.apply_loaded_weather_state({"current_weather": "snow", "current_intensity": "strong"})
        self.assertEqual(manager.current_weather, "snow")
        self.assertEqual(manager.current_intensity, "strong")

    def test_apply_loaded_weather_state_with_none_is_a_noop(self):
        manager = WeatherManager()
        manager.current_weather = "storm"
        manager.apply_loaded_weather_state(None)
        self.assertEqual(manager.current_weather, "storm")

    def test_apply_loaded_weather_state_with_non_dict_is_a_noop(self):
        manager = WeatherManager()
        manager.current_weather = "storm"
        manager.apply_loaded_weather_state("not a dict")
        self.assertEqual(manager.current_weather, "storm")


if __name__ == "__main__":
    unittest.main()
