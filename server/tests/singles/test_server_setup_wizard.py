import unittest
from pathlib import Path

from engine.server.feature_profile import FeatureProfile
from engine.server.server_config import resolve_server_settings
from engine.server.server_setup_wizard import (
    build_server_bootstrap_artifacts,
    list_wizard_presets,
)

FANTASY_FRONTIER = str(Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier")


class TestServerSetupWizard(unittest.TestCase):
    def test_lists_expected_presets(self) -> None:
        presets = list_wizard_presets()
        self.assertIn("static_world", presets)
        self.assertIn("social_no_combat", presets)
        self.assertIn("creator_sandbox", presets)

    def test_static_world_preset_builds_readonly_profile(self) -> None:
        artifact = build_server_bootstrap_artifacts("static_world", server_name="My Static", content_set_path=FANTASY_FRONTIER)
        profile = FeatureProfile.from_dict(artifact["profile_payload"])
        self.assertEqual("disabled", profile.combat_mode)
        self.assertEqual("disabled", profile.weather_mode)
        self.assertEqual("readonly", profile.world_mutation_mode)
        settings = resolve_server_settings(
            "tcp", artifact["config_payload"], None, None, None, None, None, None, artifact["config_filename"]
        )
        self.assertEqual("minimal", settings.session_authz_detail_level)
        self.assertEqual([], settings.world_bootstrap_starter_items)
        self.assertEqual([], settings.session_default_capabilities)
        self.assertEqual([], settings.session_default_entitlements)
        self.assertEqual(artifact["profile_path"], settings.feature_profile_path)

    def test_social_preset_sets_placeholder_gm_token_when_missing(self) -> None:
        artifact = build_server_bootstrap_artifacts("social_no_combat", server_name="Social Hub", content_set_path=FANTASY_FRONTIER)
        settings = resolve_server_settings(
            "tcp", artifact["config_payload"], None, None, None, None, None, None, artifact["config_filename"]
        )
        self.assertEqual("replace-with-strong-token", settings.session_gm_auth_token)
        self.assertEqual([], settings.world_bootstrap_starter_items)
        profile = FeatureProfile.from_dict(artifact["profile_payload"])
        self.assertEqual("disabled", profile.combat_mode)
        self.assertEqual("gm_only", profile.authoring_mode)

    def test_creator_sandbox_preset_enables_authoring_and_operator_entitlements(self) -> None:
        artifact = build_server_bootstrap_artifacts(
            "creator_sandbox",
            server_name="Builder Lab",
            content_set_path=FANTASY_FRONTIER,
            gm_auth_token="",
        )
        settings = resolve_server_settings(
            "tcp", artifact["config_payload"], None, None, None, None, None, None, artifact["config_filename"]
        )
        self.assertIn("authoring.gm", settings.session_default_capabilities)
        self.assertIn("creator_sdk.authoring", settings.session_default_entitlements)
        self.assertIn("operator.world.debug", settings.session_default_entitlements)
        self.assertEqual("full", settings.session_authz_detail_level)
        profile = FeatureProfile.from_dict(artifact["profile_payload"])
        self.assertEqual("all", profile.authoring_mode)
        self.assertEqual("mutable", profile.world_mutation_mode)

    def test_unknown_preset_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_server_bootstrap_artifacts("not_a_preset", server_name="X", content_set_path=FANTASY_FRONTIER)

    def test_blank_server_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_server_bootstrap_artifacts("static_world", server_name="   ", content_set_path=FANTASY_FRONTIER)

    def test_content_set_path_without_manifest_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_server_bootstrap_artifacts(
                "static_world", server_name="X", content_set_path=str(Path(__file__).resolve().parent),
            )


if __name__ == "__main__":
    unittest.main()
