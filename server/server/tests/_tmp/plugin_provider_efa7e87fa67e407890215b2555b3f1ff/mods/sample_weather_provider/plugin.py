class SampleWeatherProvider:
    mode = "custom"
    provider_id = "sample.weather.static_clear"

    def on_time_period_change(self, server, season: str) -> None:
        # Simple deterministic sample: force clear/mild weather.
        server.weather_manager.current_weather = "clear"
        server.weather_manager.current_intensity = "mild"


def setup(api):
    api.register_weather_provider("sample.weather.static_clear", SampleWeatherProvider())
