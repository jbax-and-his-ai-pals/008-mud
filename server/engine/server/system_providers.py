from __future__ import annotations

from typing import Any, Dict, List, Protocol


class WeatherProvider(Protocol):
    mode: str

    def on_time_period_change(self, server: Any, season: str) -> None:
        ...


class BuiltinWeatherProvider:
    mode = "builtin"
    provider_id = "builtin.weather.default"

    def on_time_period_change(self, server: Any, season: str) -> None:
        server.weather_manager.update_on_time_period_change(season)


class DisabledWeatherProvider:
    mode = "disabled"
    provider_id = "disabled.weather"

    def on_time_period_change(self, server: Any, season: str) -> None:
        return


class CustomWeatherProvider:
    mode = "custom"
    provider_id = "custom.weather.noop"

    def on_time_period_change(self, server: Any, season: str) -> None:
        # Placeholder hook for plugin-injected weather providers.
        return


class WorldEffectsProvider(Protocol):
    mode: str

    def tick(self, server: Any, session_id: str) -> List[Dict[str, Any]]:
        ...


class BuiltinWorldEffectsProvider:
    mode = "builtin"
    provider_id = "builtin.world_effects.default"

    def tick(self, server: Any, session_id: str) -> List[Dict[str, Any]]:
        return server._tick_world_effects_builtin(session_id)


class DisabledWorldEffectsProvider:
    mode = "disabled"
    provider_id = "disabled.world_effects"

    def tick(self, server: Any, session_id: str) -> List[Dict[str, Any]]:
        return []


class CustomWorldEffectsProvider:
    mode = "custom"
    provider_id = "custom.world_effects.noop"

    def tick(self, server: Any, session_id: str) -> List[Dict[str, Any]]:
        # Placeholder hook for plugin-injected world-effects providers.
        return []
