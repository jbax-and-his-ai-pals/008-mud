import json
import os
import tempfile
import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestSystemProviders(unittest.TestCase):
    def _make_profile(self, payload: dict) -> str:
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        try:
            json.dump(payload, tmp)
            return tmp.name
        finally:
            tmp.close()

    def test_builtin_providers_selected_by_default(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            self.assertEqual("builtin", server.weather_provider.mode)
            self.assertEqual("builtin", server.world_effects_provider.mode)
        finally:
            server.shutdown()

    def test_custom_provider_modes_attach_noop_with_warning(self) -> None:
        # Mods disabled so no plugin-registered provider can fill the gap;
        # the server must warn that no custom provider is available.
        profile_path = self._make_profile({
            "weather": {"mode": "custom"},
            "world_effects": {"mode": "custom"},
            "mods": {"mode": "disabled"},
        })
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, feature_profile_path=profile_path)
        try:
            self.assertEqual("custom", server.weather_provider.mode)
            self.assertEqual("custom", server.world_effects_provider.mode)
            warning_blob = "\n".join(server.boot_warnings).lower()
            self.assertIn("weather provider mode 'custom'", warning_blob)
            self.assertIn("world-effects provider mode 'custom'", warning_blob)
        finally:
            server.shutdown()
            os.remove(profile_path)

    def test_custom_world_field_provider_is_noop(self) -> None:
        profile_path = self._make_profile({"world_effects": {"mode": "custom"}, "mods": {"mode": "disabled"}})
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, feature_profile_path=profile_path)
        session = server.create_session()
        try:
            events = server.tick(session.session_id, 1.0)
            self.assertFalse(any(event.get("type") == "world_state" for event in events))
        finally:
            server.shutdown()
            os.remove(profile_path)

    def test_registered_custom_weather_provider_is_selected(self) -> None:
        profile_path = self._make_profile({"weather": {"mode": "custom", "provider_id": "mod.weather.test"}})
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, feature_profile_path=profile_path)
        try:
            class TestWeatherProvider:
                mode = "custom"
                provider_id = "mod.weather.test"

                def on_time_period_change(self, server_ref, season: str) -> None:
                    return

            server.register_weather_provider("mod.weather.test", TestWeatherProvider())
            server._sync_providers_with_profile()
            self.assertEqual("mod.weather.test", getattr(server.weather_provider, "provider_id", ""))
        finally:
            server.shutdown()
            os.remove(profile_path)

    def test_registered_custom_world_effects_provider_is_selected(self) -> None:
        profile_path = self._make_profile({"world_effects": {"mode": "custom", "provider_id": "mod.effects.test"}})
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, feature_profile_path=profile_path)
        try:
            class TestEffectsProvider:
                mode = "custom"
                provider_id = "mod.effects.test"

                def tick(self, server_ref, session_id: str):
                    return []

            server.register_world_effects_provider("mod.effects.test", TestEffectsProvider())
            server._sync_providers_with_profile()
            self.assertEqual("mod.effects.test", getattr(server.world_effects_provider, "provider_id", ""))
        finally:
            server.shutdown()
            os.remove(profile_path)


if __name__ == "__main__":
    unittest.main()
