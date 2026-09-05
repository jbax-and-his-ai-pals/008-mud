# tests/singles/test_system_providers_full.py
"""Coverage for engine/server/system_providers.py's concrete weather
provider classes (Builtin/Disabled/Custom), none of which are exercised
elsewhere (only their WorldEffects counterparts are).

Note: WeatherProvider/WorldEffectsProvider's `...` Protocol stub bodies are
never executed -- Protocol classes are structural, never instantiated
directly, matching this codebase's established precedent for dead code."""

import unittest
from unittest.mock import MagicMock

from engine.server.system_providers import (
    BuiltinWeatherProvider, DisabledWeatherProvider, CustomWeatherProvider,
)


class TestWeatherProviders(unittest.TestCase):
    def test_builtin_delegates_to_weather_manager(self):
        server = MagicMock()
        BuiltinWeatherProvider().on_time_period_change(server, "summer")
        server.weather_manager.update_on_time_period_change.assert_called_once_with("summer")

    def test_disabled_is_a_noop(self):
        server = MagicMock()
        DisabledWeatherProvider().on_time_period_change(server, "summer")
        server.weather_manager.update_on_time_period_change.assert_not_called()

    def test_custom_is_a_noop(self):
        server = MagicMock()
        CustomWeatherProvider().on_time_period_change(server, "summer")
        server.weather_manager.update_on_time_period_change.assert_not_called()


if __name__ == "__main__":
    unittest.main()
