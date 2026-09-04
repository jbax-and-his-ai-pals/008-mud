import unittest
import time

from poc_server import JsonLineMudServer
from tests.fixtures import FANTASY_FRONTIER


class TestServerPolicyPayload(unittest.TestCase):
    def setUp(self) -> None:
        self.app = JsonLineMudServer("127.0.0.1", 0, "test_save.json", content_set_path=FANTASY_FRONTIER)

    def tearDown(self) -> None:
        self.app.shutdown()

    def test_default_policy_payload(self) -> None:
        payload = self.app.build_server_policy_payload()
        self.assertEqual("persistent_shard", payload["profile_modes"]["world"])
        self.assertEqual("enabled", payload["profile_modes"]["combat"])
        self.assertEqual("builtin", payload["profile_modes"]["weather"])
        self.assertEqual("enabled", payload["profile_modes"]["world_effects"])
        self.assertEqual("all", payload["profile_modes"]["authoring"])
        self.assertEqual("mutable", payload["profile_modes"]["world_mutation"])
        self.assertEqual("enabled", payload["profile_modes"]["mods"])
        self.assertTrue(payload["feature_flags"]["authoring_allowed"])
        self.assertTrue(payload["feature_flags"]["world_mutation_allowed"])
        self.assertTrue(payload["feature_flags"]["weather_enabled"])
        self.assertTrue(payload["feature_flags"]["world_effects_enabled"])
        self.assertTrue(payload["feature_flags"]["combat_enabled"])
        self.assertFalse(payload["feature_flags"]["party_supported"])
        self.assertTrue(payload["feature_flags"]["persistent_world"])
        self.assertFalse(payload["party_policy"]["enabled"])
        self.assertTrue(payload["shard_policy"]["enabled"])
        self.assertEqual("enabled", payload["shard_policy"]["session_resume_policy"])
        self.assertEqual("indefinite", payload["shard_policy"]["disconnect_timeout_policy"])
        self.assertEqual(300.0, payload["shard_policy"]["disconnect_timeout_seconds"])
        self.assertEqual("world_and_players", payload["shard_policy"]["persistence_scope"])
        self.assertEqual("enabled", payload["shard_policy"]["late_join_policy"])
        self.assertEqual("always_on", payload["shard_policy"]["world_clock_policy"])
        self.assertEqual("always_on", payload["shard_policy"]["background_simulation_policy"])
        self.assertTrue(payload["shard_policy"]["operator_locks_required"])
        self.assertEqual("normal", payload["shard_policy"]["runtime_state"])
        self.assertEqual("", payload["shard_policy"]["runtime_message"])
        self.assertTrue(payload["shard_policy"]["tick_enabled"])
        self.assertTrue(payload["shard_policy"]["gameplay_enabled"])
        self.assertTrue(payload["shard_policy"]["character_creation_enabled"])
        self.assertTrue(payload["shard_policy"]["new_session_admission_enabled"])
        self.assertEqual("", payload["shard_policy"]["new_session_admission_reason"])
        diagnostics = payload["shard_policy"]["diagnostics"]
        self.assertEqual("persistent_shard", diagnostics["world_mode"])
        self.assertEqual("normal", diagnostics["runtime_state"])
        self.assertEqual(0, diagnostics["disconnected_session_count"])
        self.assertEqual(0, diagnostics["expired_grace_window_session_count"])
        self.assertIsNone(diagnostics["last_mode_change_at"])
        self.assertEqual("", diagnostics["last_mode_changed_by_session_id"])
        self.assertIn("weather", payload["active_providers"])
        self.assertIn("world_effects", payload["active_providers"])

    def test_disabled_modes_reflected_in_feature_flags(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "readonly_archive"
        profile.combat_mode = "disabled"
        profile.weather_mode = "disabled"
        profile.world_effects_mode = "disabled"
        profile.authoring_mode = "disabled"
        profile.world_mutation_mode = "readonly"
        profile.mods_mode = "disabled"

        payload = self.app.build_server_policy_payload()
        self.assertEqual("readonly_archive", payload["profile_modes"]["world"])
        self.assertEqual("disabled", payload["profile_modes"]["combat"])
        self.assertEqual("disabled", payload["profile_modes"]["weather"])
        self.assertEqual("disabled", payload["profile_modes"]["world_effects"])
        self.assertEqual("disabled", payload["profile_modes"]["authoring"])
        self.assertEqual("readonly", payload["profile_modes"]["world_mutation"])
        self.assertEqual("disabled", payload["profile_modes"]["mods"])
        self.assertFalse(payload["feature_flags"]["authoring_allowed"])
        self.assertFalse(payload["feature_flags"]["world_mutation_allowed"])
        self.assertFalse(payload["feature_flags"]["weather_enabled"])
        self.assertFalse(payload["feature_flags"]["world_effects_enabled"])
        self.assertFalse(payload["feature_flags"]["combat_enabled"])
        self.assertFalse(payload["feature_flags"]["party_supported"])
        self.assertFalse(payload["feature_flags"]["persistent_world"])
        self.assertFalse(payload["shard_policy"]["enabled"])

    def test_co_op_party_policy_flags(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "co_op_party"

        payload = self.app.build_server_policy_payload()
        self.assertEqual("co_op_party", payload["profile_modes"]["world"])
        self.assertTrue(payload["feature_flags"]["party_supported"])
        self.assertTrue(payload["party_policy"]["enabled"])
        self.assertTrue(payload["party_policy"]["invite_required"])
        self.assertTrue(payload["party_policy"]["decline_supported"])
        self.assertTrue(payload["party_policy"]["cancel_supported"])
        self.assertEqual("replace_existing", payload["party_policy"]["invite_conflict_policy"])
        self.assertTrue(payload["party_policy"]["offline_invites_supported"])
        self.assertEqual("leader_driven", payload["party_policy"]["shared_quest_policy"])
        self.assertEqual("split", payload["party_policy"]["shared_rewards_policy"])
        self.assertEqual("round_robin", payload["party_policy"]["loot_policy"])
        self.assertFalse(payload["shard_policy"]["enabled"])

    def test_co_op_party_policy_uses_raw_profile_overrides(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "co_op_party"
        profile.raw = {
            "party": {
                "shared_quest_policy": "mirror_all",
                "shared_rewards_policy": "leader_claims",
                "loot_policy": "leader_discretion",
                "invite_conflict_policy": "replace_existing",
                "offline_invites_supported": False,
            }
        }

        payload = self.app.build_server_policy_payload()
        self.assertEqual("replace_existing", payload["party_policy"]["invite_conflict_policy"])
        self.assertFalse(payload["party_policy"]["offline_invites_supported"])
        self.assertEqual("mirror_all", payload["party_policy"]["shared_quest_policy"])
        self.assertEqual("leader_claims", payload["party_policy"]["shared_rewards_policy"])
        self.assertEqual("leader_discretion", payload["party_policy"]["loot_policy"])

    def test_finite_adventure_policy_payload(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "finite_adventure"
        profile.raw = {
            "finite_adventure": {
                "default_campaign_id": "intro_story",
                "replay_supported": True,
                "checkpoint_policy": "manual_save",
            }
        }
        session_id = self.app.server.create_session(player_id="story_player").session_id
        self.app.server.execute_command(session_id, "char create StoryHero")

        payload = self.app.build_server_policy_payload(session_id)
        self.assertEqual("finite_adventure", payload["profile_modes"]["world"])
        self.assertIn("adventure_policy", payload)
        self.assertTrue(payload["adventure_policy"]["enabled"])
        self.assertEqual("intro_story", payload["adventure_policy"]["default_campaign_id"])
        self.assertTrue(payload["adventure_policy"]["replay_supported"])
        self.assertEqual("manual_save", payload["adventure_policy"]["checkpoint_policy"])
        self.assertEqual("not_started", payload["adventure_policy"]["run_state"]["status"])
        self.assertFalse(payload["adventure_policy"]["run_state"]["checkpoint_available"])
        self.assertFalse(payload["adventure_policy"]["run_state"]["last_summary_available"])

    def test_persistent_shard_policy_uses_raw_profile_overrides(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "persistent_shard"
        profile.raw = {
            "persistent_shard": {
                "session_resume_policy": "enabled",
                "disconnect_timeout_policy": "grace_window",
                "disconnect_timeout_seconds": 45,
                "persistence_scope": "world_players_and_locks",
                "late_join_policy": "enabled",
                "world_clock_policy": "always_on",
                "background_simulation_policy": "always_on",
                "operator_locks_required": False,
                "initial_runtime_state": "maintenance",
                "initial_runtime_message": "Rolling restart",
            }
        }
        self.app.server._shard_runtime_state = self.app.server._resolve_initial_shard_runtime_state()
        self.app.server._shard_runtime_message = self.app.server._resolve_initial_shard_runtime_message()

        payload = self.app.build_server_policy_payload()
        self.assertTrue(payload["shard_policy"]["enabled"])
        self.assertEqual("enabled", payload["shard_policy"]["session_resume_policy"])
        self.assertEqual("grace_window", payload["shard_policy"]["disconnect_timeout_policy"])
        self.assertEqual(45.0, payload["shard_policy"]["disconnect_timeout_seconds"])
        self.assertEqual("world_players_and_locks", payload["shard_policy"]["persistence_scope"])
        self.assertEqual("enabled", payload["shard_policy"]["late_join_policy"])
        self.assertEqual("always_on", payload["shard_policy"]["world_clock_policy"])
        self.assertEqual("always_on", payload["shard_policy"]["background_simulation_policy"])
        self.assertFalse(payload["shard_policy"]["operator_locks_required"])
        self.assertEqual("maintenance", payload["shard_policy"]["runtime_state"])
        self.assertEqual("Rolling restart", payload["shard_policy"]["runtime_message"])
        self.assertFalse(payload["shard_policy"]["tick_enabled"])
        self.assertFalse(payload["shard_policy"]["gameplay_enabled"])
        self.assertFalse(payload["shard_policy"]["character_creation_enabled"])
        self.assertFalse(payload["shard_policy"]["new_session_admission_enabled"])
        self.assertIn("maintenance", payload["shard_policy"]["new_session_admission_reason"].lower())
        diagnostics = payload["shard_policy"]["diagnostics"]
        self.assertEqual("maintenance", diagnostics["runtime_state"])
        self.assertEqual("Rolling restart", diagnostics["runtime_message"])

    def test_shard_runtime_override_replaces_initial_profile_state(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "persistent_shard"
        profile.raw = {
            "persistent_shard": {
                "initial_runtime_state": "maintenance",
                "initial_runtime_message": "Rolling restart",
            }
        }
        self.app.server._shard_runtime_state = self.app.server._resolve_initial_shard_runtime_state()
        self.app.server._shard_runtime_message = self.app.server._resolve_initial_shard_runtime_message()

        ok, _message = self.app.server.set_shard_runtime_state("normal", "", changed_by_session_id="operator-session")
        self.assertTrue(ok)

        payload = self.app.build_server_policy_payload()
        self.assertEqual("normal", payload["shard_policy"]["runtime_state"])
        self.assertEqual("", payload["shard_policy"]["runtime_message"])
        diagnostics = payload["shard_policy"]["diagnostics"]
        self.assertEqual("normal", diagnostics["runtime_state"])
        self.assertEqual("", diagnostics["runtime_message"])
        self.assertEqual("operator-session", diagnostics["last_mode_changed_by_session_id"])

    def test_shard_policy_diagnostics_include_session_pressure_and_mode_change_metadata(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "persistent_shard"
        profile.raw = {"persistent_shard": {"disconnect_timeout_policy": "grace_window", "disconnect_timeout_seconds": 60}}
        leader_session_id = self.app.server.create_session(entitlements=["operator.shard.manage"]).session_id
        follower_session_id = self.app.server.create_session().session_id
        self.app.server.mark_session_connected(leader_session_id)
        self.app.server.mark_session_disconnected(follower_session_id)
        follower_session = self.app.server.sessions[follower_session_id]
        follower_session.disconnected_at = time.time()
        self.app.server.set_shard_runtime_state("drain", "Queue shutdown", changed_by_session_id=leader_session_id)

        payload = self.app.build_server_policy_payload()
        diagnostics = payload["shard_policy"]["diagnostics"]
        self.assertEqual(2, diagnostics["total_session_count"])
        self.assertEqual(1, diagnostics["connected_session_count"])
        self.assertEqual(1, diagnostics["disconnected_session_count"])
        self.assertEqual(1, diagnostics["resumable_session_count"])
        self.assertEqual(0, diagnostics["expired_grace_window_session_count"])
        self.assertEqual(60.0, diagnostics["grace_window_seconds"])
        self.assertGreaterEqual(diagnostics["last_mode_change_at"], 0.0)
        self.assertEqual(leader_session_id, diagnostics["last_mode_changed_by_session_id"])

    def test_shard_policy_blocks_new_session_admission_when_late_join_disabled_after_start(self) -> None:
        profile = self.app.server.feature_profile
        profile.world_mode = "persistent_shard"
        profile.raw = {"persistent_shard": {"late_join_policy": "disabled"}}
        seeded_session_id = self.app.server.create_session().session_id
        self.app.server.execute_command(seeded_session_id, "char create Seeder")

        payload = self.app.build_server_policy_payload()
        self.assertFalse(payload["shard_policy"]["new_session_admission_enabled"])
        self.assertIn("cannot join", payload["shard_policy"]["new_session_admission_reason"].lower())
        diagnostics = payload["shard_policy"]["diagnostics"]
        self.assertFalse(diagnostics["new_session_admission_enabled"])

    def test_active_provider_ids_reflect_custom_registration(self) -> None:
        class DummyWeatherProvider:
            mode = "custom"
            provider_id = "mod.weather.test"

            def on_time_period_change(self, server_ref, season: str) -> None:
                return

        profile = self.app.server.feature_profile
        profile.weather_mode = "custom"
        profile.raw = {"weather": {"mode": "custom", "provider_id": "mod.weather.test"}}
        self.app.server.register_weather_provider("mod.weather.test", DummyWeatherProvider())
        payload = self.app.build_server_policy_payload()
        self.assertEqual("mod.weather.test", payload["active_providers"]["weather"])

    def test_operator_policy_payload_includes_source_and_policy(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=FANTASY_FRONTIER,
            feature_profile_path="server/data/profiles/static_world.profile.json",
        )
        self.addCleanup(app.shutdown)
        payload = app.build_operator_policy_payload()
        self.assertIn("profile_source_path", payload)
        self.assertIn("boot_warnings", payload)
        self.assertIn("boot_warnings_structured", payload)
        self.assertIn("startup_diagnostics", payload)
        self.assertIn("server_policy", payload)
        self.assertEqual(
            "server/data/profiles/static_world.profile.json",
            payload["profile_source_path"],
        )
        self.assertIn("profile_modes", payload["server_policy"])
        self.assertIsInstance(payload["boot_warnings_structured"], list)

    def test_boot_warnings_are_structured_and_deduped(self) -> None:
        self.app.server.add_boot_warning("test.duplicate", "Duplicate warning", "test")
        self.app.server.add_boot_warning("test.duplicate", "Duplicate warning", "test")
        self.assertEqual(
            1,
            len([w for w in self.app.server.boot_warnings if w == "Duplicate warning"]),
        )
        structured = [
            w for w in getattr(self.app.server, "boot_warning_records", []) if w.get("code") == "test.duplicate"
        ]
        self.assertEqual(1, len(structured))

    def test_server_policy_command_aliases(self) -> None:
        self.assertTrue(self.app._is_server_policy_command("server policy"))
        self.assertTrue(self.app._is_server_policy_command("@server policy"))
        self.assertTrue(self.app._is_server_policy_command("policy"))
        self.assertFalse(self.app._is_server_policy_command("status"))

    def test_profile_list_and_apply_command_parsing(self) -> None:
        self.assertTrue(self.app._is_profile_list_command("profile list"))
        self.assertTrue(self.app._is_profile_list_command("profiles"))
        self.assertFalse(self.app._is_profile_list_command("profile apply static_world"))
        self.assertEqual("static_world", self.app._parse_profile_apply_command("profile apply static_world"))
        self.assertEqual("", self.app._parse_profile_apply_command("profile apply"))

    def test_profile_preset_listing_contains_baselines(self) -> None:
        presets = self.app._list_profile_presets()
        self.assertIn("static_world", presets)
        self.assertIn("creative_world", presets)
        self.assertIn("social_no_combat", presets)
        self.assertIn("mobile_low_fx", presets)

    def test_apply_profile_preset_updates_policy(self) -> None:
        ok, message = self.app._apply_profile_preset("static_world")
        self.assertTrue(ok)
        self.assertIn("Profile applied", message)
        payload = self.app.build_server_policy_payload()
        self.assertEqual("readonly", payload["profile_modes"]["world_mutation"])
        self.assertEqual("disabled", payload["profile_modes"]["authoring"])


if __name__ == "__main__":
    unittest.main()
