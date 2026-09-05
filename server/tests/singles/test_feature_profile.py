import json
import os
import tempfile
import unittest
from pathlib import Path

from engine.server.feature_profile import FeatureProfile
from engine.server.headless_server import HeadlessServer

FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestFeatureProfile(unittest.TestCase):
    def test_load_profile_from_json(self) -> None:
        payload = {
            "combat": {"mode": "disabled"},
            "weather": {"mode": "disabled"},
            "world_effects": {"mode": "disabled"},
            "authoring": {"mode": "disabled"},
            "world_mutation": {"mode": "readonly"},
            "mods": {"mode": "disabled"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        try:
            profile = FeatureProfile.load(tmp_path)
        finally:
            os.remove(tmp_path)

        self.assertEqual("disabled", profile.combat_mode)
        self.assertEqual("readonly_archive", profile.resolved_world_mode())
        self.assertEqual("disabled", profile.weather_mode)
        self.assertEqual("disabled", profile.world_effects_mode)
        self.assertEqual("disabled", profile.authoring_mode)
        self.assertEqual("readonly", profile.world_mutation_mode)
        self.assertEqual("disabled", profile.mods_mode)
        self.assertFalse(profile.authoring_allowed())
        self.assertFalse(profile.world_mutation_allowed())
        self.assertFalse(profile.weather_enabled())
        self.assertFalse(profile.world_effects_enabled())

    def test_world_effects_disabled_blocks_world_state_events(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        session = server.create_session()
        server.feature_profile.world_effects_mode = "disabled"
        events = server.tick(session.session_id, 1.0)
        server.shutdown()

        self.assertFalse(any(event.get("type") == "world_state" for event in events))

    def test_invalid_modes_fall_back_with_warnings(self) -> None:
        payload = {
            "combat": {"mode": "bad"},
            "weather": {"mode": "stormy"},
            "world_effects": {"mode": "mystery"},
            "authoring": {"mode": "sometimes"},
            "world_mutation": {"mode": "on"},
            "mods": {"mode": "third_party"},
        }
        profile = FeatureProfile.from_dict(payload)
        self.assertEqual("enabled", profile.combat_mode)
        self.assertEqual("builtin", profile.weather_mode)
        self.assertEqual("enabled", profile.world_effects_mode)
        self.assertEqual("all", profile.authoring_mode)
        self.assertEqual("mutable", profile.world_mutation_mode)
        self.assertEqual("enabled", profile.mods_mode)
        self.assertEqual(6, len(profile.warnings))

    def test_world_effects_mode_is_read_directly(self) -> None:
        payload = {"world_effects": {"mode": "custom"}}
        profile = FeatureProfile.from_dict(payload)
        self.assertEqual("custom", profile.world_effects_mode)

    def test_world_mode_explicit_parse(self) -> None:
        payload = {"world": {"mode": "co_op_party"}}
        profile = FeatureProfile.from_dict(payload)
        self.assertEqual("co_op_party", profile.resolved_world_mode())

    def test_finite_adventure_world_mode_explicit_parse(self) -> None:
        payload = {"world": {"mode": "finite_adventure"}}
        profile = FeatureProfile.from_dict(payload)
        self.assertEqual("finite_adventure", profile.resolved_world_mode())

    def test_combat_disabled_blocks_combat_commands(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        session = server.create_session()
        server.execute_command(session.session_id, "char create TestPlayer")
        server.feature_profile.combat_mode = "disabled"
        events = server.execute_command(session.session_id, "combat")
        server.shutdown()

        text_payloads = [str(event.get("payload", "")) for event in events if event.get("type") == "text"]
        self.assertTrue(any("do not have permission" in payload.lower() for payload in text_payloads))

    def test_single_player_story_blocks_secondary_session_commands(self) -> None:
        payload = {
            "world": {"mode": "single_player_story"},
            "combat": {"mode": "enabled"},
            "world_mutation": {"mode": "mutable"},
            "authoring": {"mode": "all"},
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = tmp.name
        try:
            server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), feature_profile_path=tmp_path)
            primary = server.create_session()
            secondary = server.create_session()
            server.execute_command(primary.session_id, "char create Primary")
            server.execute_command(secondary.session_id, "char create Secondary")
            blocked = server.execute_command(secondary.session_id, "look")
            allowed = server.execute_command(primary.session_id, "look")
        finally:
            server.shutdown()
            os.remove(tmp_path)

        blocked_text = [str(event.get("payload", "")) for event in blocked if event.get("type") == "text"]
        allowed_text = [str(event.get("payload", "")) for event in allowed if event.get("type") == "text"]
        self.assertTrue(any("single_player_story" in payload for payload in blocked_text))
        self.assertFalse(any("single_player_story" in payload for payload in allowed_text))


class TestFeatureProfileEdgeCases(unittest.TestCase):
    def test_non_dict_category_value_falls_back_to_default(self) -> None:
        profile = FeatureProfile.from_dict({"combat": "not a dict"})
        self.assertEqual(profile.combat_mode, "enabled")

    def test_load_with_no_path_returns_defaults(self) -> None:
        profile = FeatureProfile.load(None)
        self.assertEqual(profile.combat_mode, "enabled")

    def test_load_with_missing_file_returns_defaults(self) -> None:
        profile = FeatureProfile.load("/totally/bogus/missing/profile.json")
        self.assertEqual(profile.combat_mode, "enabled")

    def test_load_with_malformed_json_returns_defaults(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            tmp.write("{not valid json")
            tmp_path = tmp.name
        try:
            profile = FeatureProfile.load(tmp_path)
        finally:
            os.remove(tmp_path)
        self.assertEqual(profile.combat_mode, "enabled")

    def test_load_with_non_dict_json_returns_defaults(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
            json.dump([1, 2, 3], tmp)
            tmp_path = tmp.name
        try:
            profile = FeatureProfile.load(tmp_path)
        finally:
            os.remove(tmp_path)
        self.assertEqual(profile.combat_mode, "enabled")

    def test_set_mode_with_invalid_value_is_rejected(self) -> None:
        profile = FeatureProfile()
        success, msg = profile.set_mode("combat", "totally_bogus_mode")
        self.assertFalse(success)
        self.assertIn("Invalid mode", msg)

    def test_permadeath_enabled(self) -> None:
        profile = FeatureProfile(permadeath_mode="enabled")
        self.assertTrue(profile.permadeath_enabled())
        profile.permadeath_mode = "disabled"
        self.assertFalse(profile.permadeath_enabled())


if __name__ == "__main__":
    unittest.main()
