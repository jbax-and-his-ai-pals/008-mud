# tests/singles/test_server_config_full.py
"""Coverage for engine/server/server_config.py: load_server_config's
existing-but-malformed and non-dict-JSON branches, and
resolve_server_settings' non-list/empty-string-skip/successful-append
branches across default_capabilities, default_entitlements,
world_bootstrap.starter_items (both string and dict entries), and
startup_diagnostics.fail_on_warning_codes."""

import json
import os
import tempfile
import unittest

from engine.server.server_config import load_server_config, resolve_server_settings


class TestLoadServerConfig(unittest.TestCase):
    def test_empty_path_returns_empty_dict(self):
        self.assertEqual(load_server_config(""), {})
        self.assertEqual(load_server_config(None), {})

    def test_malformed_json_returns_empty_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            path = f.name
        try:
            self.assertEqual(load_server_config(path), {})
        finally:
            os.remove(path)

    def test_non_dict_json_returns_empty_dict(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([1, 2, 3], f)
            path = f.name
        try:
            self.assertEqual(load_server_config(path), {})
        finally:
            os.remove(path)


def _resolve(payload):
    return resolve_server_settings("tcp", payload, None, None, None, None, None, None, None)


class TestResolveServerSettingsListFields(unittest.TestCase):
    def test_non_list_default_capabilities_is_ignored(self):
        settings = _resolve({"session": {"default_capabilities": "not a list"}})
        self.assertEqual(settings.session_default_capabilities, [])

    def test_blank_capability_entries_are_skipped(self):
        settings = _resolve({"session": {"default_capabilities": ["  ", "real_cap", ""]}})
        self.assertEqual(settings.session_default_capabilities, ["real_cap"])

    def test_non_list_default_entitlements_is_ignored(self):
        settings = _resolve({"session": {"default_entitlements": "not a list"}})
        self.assertEqual(settings.session_default_entitlements, [])

    def test_blank_entitlement_entries_are_skipped(self):
        settings = _resolve({"session": {"default_entitlements": ["  ", "real_ent"]}})
        self.assertEqual(settings.session_default_entitlements, ["real_ent"])

    def test_non_list_starter_items_is_ignored(self):
        settings = _resolve({"world_bootstrap": {"starter_items": "not a list"}})
        self.assertEqual(settings.world_bootstrap_starter_items, [])

    def test_blank_string_starter_item_is_skipped(self):
        settings = _resolve({"world_bootstrap": {"starter_items": ["   "]}})
        self.assertEqual(settings.world_bootstrap_starter_items, [])

    def test_blank_dict_starter_item_id_is_skipped(self):
        settings = _resolve({"world_bootstrap": {"starter_items": [{"item_id": "  "}]}})
        self.assertEqual(settings.world_bootstrap_starter_items, [])

    def test_multiple_valid_starter_items_are_all_kept(self):
        settings = _resolve({
            "world_bootstrap": {"starter_items": [
                "item_a",
                {"item_id": "item_b", "quantity": 3},
            ]},
        })
        self.assertEqual(
            settings.world_bootstrap_starter_items,
            ["item_a", {"item_id": "item_b", "quantity": 3}],
        )

    def test_multiple_dict_starter_items_loop_past_the_first(self):
        settings = _resolve({
            "world_bootstrap": {"starter_items": [
                {"item_id": "item_b", "quantity": 3},
                {"item_id": "item_c", "quantity": 1},
            ]},
        })
        self.assertEqual(
            settings.world_bootstrap_starter_items,
            [{"item_id": "item_b", "quantity": 3}, {"item_id": "item_c", "quantity": 1}],
        )

    def test_starter_item_entry_of_unsupported_type_is_skipped(self):
        settings = _resolve({"world_bootstrap": {"starter_items": [12345, {"item_id": "item_b"}]}})
        self.assertEqual(settings.world_bootstrap_starter_items, [{"item_id": "item_b", "quantity": 1}])

    def test_non_list_fail_on_warning_codes_is_ignored(self):
        settings = _resolve({"startup_diagnostics": {"fail_on_warning_codes": "not a list"}})
        self.assertEqual(settings.boot_warning_fail_codes, [])

    def test_blank_and_multiple_fail_codes(self):
        settings = _resolve({"startup_diagnostics": {"fail_on_warning_codes": ["  ", "CODE_A", "CODE_B"]}})
        self.assertEqual(settings.boot_warning_fail_codes, ["CODE_A", "CODE_B"])


if __name__ == "__main__":
    unittest.main()
