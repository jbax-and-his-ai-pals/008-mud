import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class _DummyProvider:
    pass


class TestConfiguredCustomProviderId(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_non_dict_raw_profile_returns_empty(self):
        self.server.feature_profile.raw = "not-a-dict"
        self.assertEqual("", self.server._configured_custom_provider_id("weather"))

    def test_non_dict_system_node_returns_empty(self):
        self.server.feature_profile.raw = {"weather": "not-a-dict"}
        self.assertEqual("", self.server._configured_custom_provider_id("weather"))

    def test_missing_system_key_returns_empty(self):
        self.server.feature_profile.raw = {}
        self.assertEqual("", self.server._configured_custom_provider_id("weather"))


class TestRegisterProviderBlankId(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_register_weather_provider_with_blank_id_is_a_no_op(self):
        before = dict(self.server.custom_weather_providers)
        self.server.register_weather_provider("   ", _DummyProvider())
        self.assertEqual(before, self.server.custom_weather_providers)

    def test_register_world_effects_provider_with_blank_id_is_a_no_op(self):
        before = dict(self.server.custom_world_effects_providers)
        self.server.register_world_effects_provider("", _DummyProvider())
        self.assertEqual(before, self.server.custom_world_effects_providers)


class TestCustomProviderFallsBackToFirstRegistered(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_weather_custom_mode_with_no_configured_id_uses_first_registered_provider(self):
        provider_b = _DummyProvider()
        provider_a = _DummyProvider()
        # Register out of alpha order to prove "first" means sorted-by-id, not insertion order.
        self.server.register_weather_provider("zzz_provider", provider_b)
        self.server.register_weather_provider("aaa_provider", provider_a)
        self.server.feature_profile.weather_mode = "custom"
        self.server.feature_profile.raw = {"weather": {}}  # no explicit provider_id
        resolved = self.server._resolve_weather_provider()
        self.assertIs(provider_a, resolved)

    def test_world_effects_custom_mode_with_no_configured_id_uses_first_registered_provider(self):
        provider_b = _DummyProvider()
        provider_a = _DummyProvider()
        self.server.register_world_effects_provider("zzz_provider", provider_b)
        self.server.register_world_effects_provider("aaa_provider", provider_a)
        self.server.feature_profile.world_effects_mode = "custom"
        self.server.feature_profile.raw = {"world_effects": {}}
        resolved = self.server._resolve_world_effects_provider("custom")
        self.assertIs(provider_a, resolved)

    def test_weather_custom_mode_with_no_providers_at_all_warns_and_returns_noop(self):
        # The sample_weather_provider mod auto-registers itself at boot, so
        # this branch (truly zero providers registered) must be forced explicitly.
        self.server.custom_weather_providers.clear()
        self.server.feature_profile.weather_mode = "custom"
        self.server.feature_profile.raw = {"weather": {}}
        before_warnings = len(self.server.boot_warning_records)
        resolved = self.server._resolve_weather_provider()
        self.assertEqual("custom", getattr(resolved, "mode", ""))
        self.assertGreater(len(self.server.boot_warning_records), before_warnings)

    def test_world_effects_custom_mode_with_no_providers_at_all_warns_and_returns_noop(self):
        self.server.custom_world_effects_providers.clear()
        self.server.feature_profile.world_effects_mode = "custom"
        self.server.feature_profile.raw = {"world_effects": {}}
        before_warnings = len(self.server.boot_warning_records)
        resolved = self.server._resolve_world_effects_provider("custom")
        self.assertEqual("custom", getattr(resolved, "mode", ""))
        self.assertGreater(len(self.server.boot_warning_records), before_warnings)


class TestEffectiveWorldEffectsMode(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))

    def tearDown(self) -> None:
        self.server.shutdown()

    def test_reflects_feature_profile_mode(self):
        self.server.feature_profile.world_effects_mode = "disabled"
        self.assertEqual("disabled", self.server._effective_world_effects_mode())


if __name__ == "__main__":
    unittest.main()
