import json
import os
import shutil
import unittest
import uuid

from engine.server.headless_server import HeadlessServer
from engine.server.feature_profile import FeatureProfile
from tests.fixtures import FANTASY_FRONTIER


class TestPluginProviderIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_root = os.path.abspath(
            os.path.join("server", "tests", "_tmp", f"plugin_provider_{uuid.uuid4().hex}")
        )
        os.makedirs(self._tmp_root, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def test_sample_weather_provider_loads_and_applies(self) -> None:
        mods_dir = os.path.join(self._tmp_root, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        src_mod = os.path.abspath(os.path.join("mods", "sample_weather_provider"))
        dst_mod = os.path.join(mods_dir, "sample_weather_provider")
        shutil.copytree(src_mod, dst_mod)

        profile_path = os.path.join(self._tmp_root, "profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "weather": {
                        "mode": "custom",
                        "provider_id": "sample.weather.static_clear",
                    },
                    "mods": {"mode": "enabled"},
                },
                f,
            )

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            feature_profile=FeatureProfile.load(profile_path),
            mods_dir=mods_dir,
        )
        try:
            self.assertEqual(
                "sample.weather.static_clear",
                getattr(server.weather_provider, "provider_id", ""),
            )
            server.weather_manager.current_weather = "storm"
            server.weather_manager.current_intensity = "severe"
            server.weather_provider.on_time_period_change(server, "summer")
            self.assertEqual("clear", server.weather_manager.current_weather)
            self.assertEqual("mild", server.weather_manager.current_intensity)
        finally:
            server.shutdown()

    def test_sample_world_effects_provider_loads_and_applies(self) -> None:
        mods_dir = os.path.join(self._tmp_root, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        src_mod = os.path.abspath(os.path.join("mods", "sample_world_effects_provider"))
        dst_mod = os.path.join(mods_dir, "sample_world_effects_provider")
        shutil.copytree(src_mod, dst_mod)

        profile_path = os.path.join(self._tmp_root, "profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "world_effects": {
                        "mode": "custom",
                        "provider_id": "sample.effects.balance",
                    },
                    "mods": {"mode": "enabled"},
                },
                f,
            )

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            feature_profile=FeatureProfile.load(profile_path),
            mods_dir=mods_dir,
        )
        session = server.create_session()
        try:
            self.assertEqual(
                "sample.effects.balance",
                getattr(server.world_effects_provider, "provider_id", ""),
            )
            events = server.tick(session.session_id, 1.0)
            events.extend(server._flush_background_batch(session.session_id))
            world_state = [evt for evt in events if evt.get("type") == "world_state"]
            self.assertTrue(world_state)
            systems = {str(evt.get("payload", {}).get("system", "")) for evt in world_state}
            self.assertIn("world_effects", systems)
            effects = {
                effect
                for event in world_state
                for effect in event.get("payload", {}).get("effects", [])
            }
            self.assertTrue({"pressure", "relief"}.issubset(effects))
        finally:
            server.shutdown()

    def test_plugin_provider_no_spurious_boot_warning(self) -> None:
        """When a plugin registers the exact provider_id configured in the profile,
        no 'not found' warning should appear in boot_warnings.

        This specifically guards against the pre-init-order-fix regression where
        providers were resolved before plugins loaded, generating a false warning
        that stayed in boot_warnings even after the plugin later registered it.
        """
        mods_dir = os.path.join(self._tmp_root, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        src_mod = os.path.abspath(os.path.join("mods", "sample_world_effects_provider"))
        dst_mod = os.path.join(mods_dir, "sample_world_effects_provider")
        shutil.copytree(src_mod, dst_mod)

        profile_path = os.path.join(self._tmp_root, "profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "world_effects": {
                        "mode": "custom",
                        "provider_id": "sample.effects.balance",
                    },
                    "mods": {"mode": "enabled"},
                },
                f,
            )

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            feature_profile=FeatureProfile.load(profile_path),
            mods_dir=mods_dir,
        )
        try:
            # Provider must resolve correctly.
            self.assertEqual(
                "sample.effects.balance",
                getattr(server.world_effects_provider, "provider_id", ""),
            )
            # No "not found" warning should have been emitted.
            warning_blob = "\n".join(server.boot_warnings).lower()
            self.assertNotIn(
                "sample.effects.balance",
                warning_blob,
                msg="Expected no 'not found' boot warning when plugin provides the configured provider.",
            )
            self.assertNotIn(
                "not found",
                warning_blob,
                msg="Unexpected 'not found' boot warning in: %s" % warning_blob,
            )
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
