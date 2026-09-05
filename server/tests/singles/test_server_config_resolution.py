import unittest
from pathlib import Path

from engine.server.server_config import load_server_config, resolve_server_settings


class TestServerConfigResolution(unittest.TestCase):
    def test_load_server_config_missing_returns_empty(self) -> None:
        cfg = load_server_config("C:/definitely/missing/server_config.json")
        self.assertEqual({}, cfg)

    def test_defaults_when_no_config_and_no_cli(self) -> None:
        settings = resolve_server_settings(
            "tcp", {}, None, None, None, None, None
        )
        self.assertEqual("127.0.0.1", settings.host)
        self.assertEqual(8765, settings.port)
        self.assertEqual("server_save.json", settings.save_file)
        self.assertEqual(":memory:", settings.asset_db)
        self.assertEqual([], settings.session_default_capabilities)
        self.assertEqual([], settings.session_default_entitlements)
        self.assertEqual("full", settings.session_authz_detail_level)
        self.assertIsNone(settings.session_gm_auth_token)
        self.assertEqual({}, settings.entitlement_policy)
        self.assertEqual(512, settings.abuse_max_command_chars)
        self.assertEqual(8192, settings.abuse_max_envelope_bytes)
        self.assertEqual(8.0, settings.abuse_command_rate_limit_per_sec)
        self.assertEqual(16, settings.abuse_command_burst)
        self.assertEqual([], settings.world_bootstrap_starter_items)
        self.assertTrue(settings.session_require_character_creation)
        self.assertEqual([], settings.boot_warning_fail_codes)

    def test_config_values_applied_when_cli_missing(self) -> None:
        payload = {
            "server": {
                "host": "0.0.0.0",
                "port": 9999,
                "save_file": "foo.json",
                "asset_db": "bar.sqlite3",
            },
            "world_bootstrap": {
                "starter_items": [
                    {"item_id": "item_starter_dagger", "quantity": 1},
                    {"item_id": "item_healing_potion_small", "quantity": 2},
                ]
            },
            "websocket": {"port": 7777},
            "session": {
                "default_capabilities": ["authoring.gm"],
                "default_entitlements": ["operator.profile.apply"],
                "require_character_creation": True,
                "authz_detail_level": "minimal",
                "gm_auth_token": "secret-token",
            },
            "entitlements": {"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
            "abuse_safeguards": {
                "max_command_chars": 256,
                "max_envelope_bytes": 4096,
                "command_rate_limit_per_sec": 4.0,
                "command_burst": 6,
            },
            "startup_diagnostics": {
                "fail_on_warning_codes": ["content.spells.dir_missing", "content.items.file_errors"],
            },
        }
        tcp_settings = resolve_server_settings(
            "tcp", payload, None, None, None, None, "server/config/server_config.json"
        )
        ws_settings = resolve_server_settings(
            "ws", payload, None, None, None, None, "server/config/server_config.json"
        )
        self.assertEqual("0.0.0.0", tcp_settings.host)
        self.assertEqual(9999, tcp_settings.port)
        self.assertEqual(7777, ws_settings.port)
        self.assertEqual("foo.json", tcp_settings.save_file)
        self.assertEqual("bar.sqlite3", tcp_settings.asset_db)
        self.assertEqual(
            [
                {"item_id": "item_starter_dagger", "quantity": 1},
                {"item_id": "item_healing_potion_small", "quantity": 2},
            ],
            tcp_settings.world_bootstrap_starter_items,
        )
        self.assertEqual(["authoring.gm"], tcp_settings.session_default_capabilities)
        self.assertEqual(["operator.profile.apply"], tcp_settings.session_default_entitlements)
        self.assertTrue(tcp_settings.session_require_character_creation)
        self.assertEqual("minimal", tcp_settings.session_authz_detail_level)
        self.assertEqual("secret-token", tcp_settings.session_gm_auth_token)
        self.assertEqual(
            {"gates": {"operator.profile.apply": {"requires": ["operator.profile.apply"]}}},
            tcp_settings.entitlement_policy,
        )
        self.assertEqual(256, tcp_settings.abuse_max_command_chars)
        self.assertEqual(4096, tcp_settings.abuse_max_envelope_bytes)
        self.assertEqual(4.0, tcp_settings.abuse_command_rate_limit_per_sec)
        self.assertEqual(6, tcp_settings.abuse_command_burst)
        self.assertEqual(
            ["content.spells.dir_missing", "content.items.file_errors"],
            tcp_settings.boot_warning_fail_codes,
        )

    def test_cli_overrides_config(self) -> None:
        payload = {
            "server": {"host": "0.0.0.0", "port": 9999, "save_file": "foo.json", "asset_db": "bar.sqlite3"},
        }
        settings = resolve_server_settings(
            "tcp",
            payload,
            "127.1.1.1",
            8123,
            "custom_save.json",
            "custom.sqlite3",
            "server/config/server_config.json",
        )
        self.assertEqual("127.1.1.1", settings.host)
        self.assertEqual(8123, settings.port)
        self.assertEqual("custom_save.json", settings.save_file)
        self.assertEqual("custom.sqlite3", settings.asset_db)
        self.assertEqual([], settings.session_default_capabilities)
        self.assertEqual([], settings.session_default_entitlements)
        self.assertEqual("full", settings.session_authz_detail_level)
        self.assertIsNone(settings.session_gm_auth_token)
        self.assertEqual({}, settings.entitlement_policy)
        self.assertEqual(512, settings.abuse_max_command_chars)
        self.assertEqual(8192, settings.abuse_max_envelope_bytes)
        self.assertEqual(8.0, settings.abuse_command_rate_limit_per_sec)
        self.assertEqual(16, settings.abuse_command_burst)
        self.assertEqual([], settings.world_bootstrap_starter_items)
        self.assertTrue(settings.session_require_character_creation)
        self.assertEqual([], settings.boot_warning_fail_codes)

    def test_locked_down_example_config_resolves_expected_profile_and_gates(self) -> None:
        cfg_path = (Path(__file__).resolve().parents[2] / "config" / "server_config.static_lockeddown.example.json")
        payload = load_server_config(str(cfg_path))
        settings = resolve_server_settings(
            "tcp",
            payload,
            None,
            None,
            None,
            None,
            str(cfg_path),
        )
        self.assertEqual([], settings.session_default_capabilities)
        self.assertEqual([], settings.session_default_entitlements)
        self.assertTrue(settings.session_require_character_creation)
        self.assertEqual("minimal", settings.session_authz_detail_level)
        self.assertIsNone(settings.session_gm_auth_token)
        gates = settings.entitlement_policy.get("gates", {})
        self.assertIn("creator_sdk.authoring", gates)
        self.assertIn("operator.profile.apply", gates)
        self.assertEqual([], settings.boot_warning_fail_codes)


if __name__ == "__main__":
    unittest.main()
