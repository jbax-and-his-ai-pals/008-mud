# tests/singles/test_plugin_manager.py
"""Coverage for engine/core/plugin_manager.py: _parse_version/_version_in_range
edge cases, PluginAPI's capability-gated methods, and PluginManager's full
discovery/load/unload lifecycle (missing manifest, invalid JSON, missing
plugin_id, manifest validation failure, missing plugin.py, missing setup(),
runtime errors during exec, successful load, and teardown on unload) --
almost none of which the existing manifest-validator tests exercise, since
those only call validate_plugin_manifest() directly."""

import io
import json
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.core.plugin_manager import (
    PluginAPI, PluginManager, PermissionError as PluginPermissionError,
    _parse_version, _version_in_range, validate_plugin_manifest,
)

VALID_MANIFEST = {
    "plugin_id": "sample_mod",
    "name": "Sample Mod",
    "version": "1.0.0",
    "manifest_schema_version": "1",
    "engine_api_min": "1.0",
    "engine_api_max": "1.0",
    "capabilities": ["command_registration"],
}


class TestParseVersion(unittest.TestCase):
    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_version(""))

    def test_whitespace_only_returns_none(self):
        self.assertIsNone(_parse_version("   "))

    def test_non_numeric_component_returns_none(self):
        self.assertIsNone(_parse_version("1.a.0"))

    def test_valid_dotted_version_parses_to_tuple(self):
        self.assertEqual((1, 2, 3), _parse_version("1.2.3"))


class TestVersionInRange(unittest.TestCase):
    def test_unparseable_current_returns_false(self):
        self.assertFalse(_version_in_range("abc", "1.0", "2.0"))

    def test_unparseable_min_returns_false(self):
        self.assertFalse(_version_in_range("1.0", "abc", "2.0"))

    def test_unparseable_max_returns_false(self):
        self.assertFalse(_version_in_range("1.0", "0.5", "abc"))

    def test_within_range_is_true(self):
        self.assertTrue(_version_in_range("1.5", "1.0", "2.0"))

    def test_outside_range_is_false(self):
        self.assertFalse(_version_in_range("3.0", "1.0", "2.0"))


class TestValidatePluginManifestDirect(unittest.TestCase):
    def test_missing_required_field_is_reported(self):
        manifest = dict(VALID_MANIFEST)
        del manifest["name"]
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("name" in e for e in errors))

    def test_blank_required_field_is_reported(self):
        manifest = dict(VALID_MANIFEST, name="   ")
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("name" in e for e in errors))

    def test_unsupported_schema_version_is_reported(self):
        manifest = dict(VALID_MANIFEST, manifest_schema_version="99")
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("Unsupported manifest_schema_version" in e for e in errors))

    def test_missing_engine_api_bounds_skips_range_check(self):
        # Blank min/max still trip the required-field check, but the
        # range-comparison logic itself (min_v and max_v) must be skipped.
        manifest = dict(VALID_MANIFEST, engine_api_min="", engine_api_max="")
        errors = validate_plugin_manifest(manifest)
        self.assertFalse(any("dotted numeric" in e or "outside plugin supported" in e or "<= engine_api_max" in e for e in errors))

    def test_non_numeric_engine_api_bounds_reported(self):
        manifest = dict(VALID_MANIFEST, engine_api_min="abc", engine_api_max="1.0")
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("dotted numeric versions" in e for e in errors))

    def test_min_greater_than_max_reported(self):
        manifest = dict(VALID_MANIFEST, engine_api_min="2.0", engine_api_max="1.0")
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("must be <= engine_api_max" in e for e in errors))

    def test_unknown_capability_is_reported(self):
        manifest = dict(VALID_MANIFEST, capabilities=["not_a_real_capability"])
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("Unknown capability" in e for e in errors))

    def test_non_list_capabilities_is_reported(self):
        manifest = dict(VALID_MANIFEST, capabilities="command_registration")
        errors = validate_plugin_manifest(manifest)
        self.assertTrue(any("must be an array" in e for e in errors))

    def test_fully_valid_manifest_has_no_errors(self):
        self.assertEqual([], validate_plugin_manifest(VALID_MANIFEST))


class TestPluginAPI(unittest.TestCase):
    def setUp(self):
        self.game = MagicMock()
        self.manifest = dict(VALID_MANIFEST, capabilities=[
            "command_registration", "world_modification", "server_broadcast",
            "system_provider_registration",
        ])
        self.api = PluginAPI(self.game, self.manifest)

    def test_plugin_id_defaults_when_missing(self):
        api = PluginAPI(self.game, {})
        self.assertEqual("unknown_plugin", api.plugin_id)

    def test_check_cap_raises_when_capability_absent(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api._check_cap("world_modification")

    def test_register_command_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.register_command("test_cmd")

    def test_register_command_returns_a_working_decorator(self):
        @self.api.register_command("plugin_test_command", aliases=["ptc"])
        def handler(context):
            return "handled"
        from engine.commands.command_system import registered_commands
        self.assertIn("plugin_test_command", registered_commands)
        registered_commands.pop("plugin_test_command", None)
        registered_commands.pop("ptc", None)

    def test_spawn_npc_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.spawn_npc("goblin", "town:square")

    def test_spawn_npc_delegates_to_world_when_available(self):
        self.game.world.spawn_npc.return_value = "spawned!"
        result = self.api.spawn_npc("goblin", "town:square")
        self.game.world.spawn_npc.assert_called_once_with("goblin", "town:square")
        self.assertEqual("spawned!", result)

    def test_spawn_npc_returns_none_when_world_lacks_spawn_npc(self):
        game = MagicMock(spec=["world"])
        game.world = MagicMock(spec=[])  # no spawn_npc attr
        api = PluginAPI(game, self.manifest)
        self.assertIsNone(api.spawn_npc("goblin", "town:square"))

    def test_broadcast_message_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.broadcast_message("hello")

    def test_broadcast_message_delegates_when_headless_server_present(self):
        self.api.broadcast_message("hello everyone")
        self.game.headless_server.broadcast.assert_called_once_with("hello everyone")

    def test_broadcast_message_is_a_no_op_without_headless_server(self):
        game = MagicMock(spec=[])
        api = PluginAPI(game, self.manifest)
        api.broadcast_message("hello")  # must not raise

    def test_register_weather_provider_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.register_weather_provider("prov1", object())

    def test_register_weather_provider_delegates_when_available(self):
        provider = object()
        self.api.register_weather_provider("prov1", provider)
        self.game.register_weather_provider.assert_called_once_with("prov1", provider)

    def test_register_weather_provider_is_a_no_op_without_support(self):
        game = MagicMock(spec=[])
        api = PluginAPI(game, self.manifest)
        api.register_weather_provider("prov1", object())  # must not raise

    def test_register_world_field_provider_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.register_world_field_provider("prov1", object())

    def test_register_world_field_provider_delegates_when_available(self):
        provider = object()
        self.api.register_world_field_provider("prov1", provider)
        self.game.register_world_field_provider.assert_called_once_with("prov1", provider)

    def test_register_world_field_provider_is_a_no_op_without_support(self):
        game = MagicMock(spec=[])
        api = PluginAPI(game, self.manifest)
        api.register_world_field_provider("prov1", object())  # must not raise

    def test_register_world_effects_provider_without_capability_raises(self):
        api = PluginAPI(self.game, dict(VALID_MANIFEST, capabilities=[]))
        with self.assertRaises(PluginPermissionError):
            api.register_world_effects_provider("prov1", object())

    def test_register_world_effects_provider_delegates_when_available(self):
        provider = object()
        self.api.register_world_effects_provider("prov1", provider)
        self.game.register_world_effects_provider.assert_called_once_with("prov1", provider)

    def test_register_world_effects_provider_is_a_no_op_without_support(self):
        game = MagicMock(spec=[])
        api = PluginAPI(game, self.manifest)
        api.register_world_effects_provider("prov1", object())  # must not raise


class TestPluginManagerLoading(unittest.TestCase):
    def _mods_root(self) -> Path:
        root = Path("tmp") / f"plugin_manager_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_manifest(self, plugin_dir: Path, manifest: dict):
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def setUp(self):
        self.game = MagicMock()

    def test_load_all_plugins_with_missing_mods_dir_is_a_no_op(self):
        mgr = PluginManager(self.game, mods_dir=str(Path("tmp") / f"does_not_exist_{uuid.uuid4().hex}"))
        mgr.load_all_plugins()  # must not raise
        self.assertEqual({}, mgr.plugins)

    def test_load_all_plugins_only_considers_directories(self):
        root = self._mods_root()
        (root / "not_a_plugin_dir.txt").write_text("hi", encoding="utf-8")
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_all_plugins()  # must not raise
        self.assertEqual({}, mgr.plugins)

    def test_load_plugin_missing_manifest_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "no_manifest_plugin"
        plugin_dir.mkdir()
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn(str(plugin_dir), mgr.load_errors)
        self.assertIn("Missing manifest.json", mgr.load_errors[str(plugin_dir)])

    def test_load_plugin_invalid_json_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "bad_json_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn("Invalid manifest.json", mgr.load_errors[str(plugin_dir)])

    def test_load_plugin_missing_plugin_id_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "no_id_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id=""))
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn("Manifest missing plugin_id", mgr.load_errors[str(plugin_dir)])

    def test_load_plugin_manifest_validation_failure_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "invalid_manifest_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="invalid_manifest_plugin", capabilities="not_a_list"))
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn("Manifest validation failed", mgr.load_errors["invalid_manifest_plugin"])

    def test_load_plugin_missing_plugin_py_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "no_script_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="no_script_plugin"))
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn("Missing plugin.py", mgr.load_errors["no_script_plugin"])

    def test_load_plugin_missing_setup_function_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "no_setup_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="no_setup_plugin"))
        (plugin_dir / "plugin.py").write_text("x = 1\n", encoding="utf-8")
        mgr = PluginManager(self.game, mods_dir=str(root))
        mgr.load_plugin(str(plugin_dir))
        self.assertIn("missing 'setup(api)' function", mgr.load_errors["no_setup_plugin"])

    def test_load_plugin_runtime_error_during_setup_records_error(self):
        root = self._mods_root()
        plugin_dir = root / "exploding_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="exploding_plugin"))
        (plugin_dir / "plugin.py").write_text(
            "def setup(api):\n    raise RuntimeError('boom')\n", encoding="utf-8",
        )
        mgr = PluginManager(self.game, mods_dir=str(root))
        with redirect_stdout(io.StringIO()):
            mgr.load_plugin(str(plugin_dir))
        self.assertIn("Runtime error during load", mgr.load_errors["exploding_plugin"])
        self.assertNotIn("exploding_plugin", mgr.plugins)

    def test_load_plugin_success_registers_plugin_and_manifest(self):
        root = self._mods_root()
        plugin_dir = root / "good_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="good_plugin"))
        (plugin_dir / "plugin.py").write_text(
            "loaded = []\ndef setup(api):\n    loaded.append(api.plugin_id)\n", encoding="utf-8",
        )
        mgr = PluginManager(self.game, mods_dir=str(root))
        with redirect_stdout(io.StringIO()):
            mgr.load_plugin(str(plugin_dir))
        self.assertIn("good_plugin", mgr.plugins)
        self.assertIn("good_plugin", mgr.manifests)
        self.assertEqual(["good_plugin"], mgr.plugins["good_plugin"].loaded)
        self.addCleanup(lambda: sys.modules.pop("good_plugin", None))

    def test_load_all_plugins_loads_every_directory_entry(self):
        root = self._mods_root()
        plugin_dir = root / "auto_discovered_plugin"
        self._write_manifest(plugin_dir, dict(VALID_MANIFEST, plugin_id="auto_discovered_plugin"))
        (plugin_dir / "plugin.py").write_text("def setup(api):\n    pass\n", encoding="utf-8")
        mgr = PluginManager(self.game, mods_dir=str(root))
        with redirect_stdout(io.StringIO()):
            mgr.load_all_plugins()
        self.assertIn("auto_discovered_plugin", mgr.plugins)
        self.addCleanup(lambda: sys.modules.pop("auto_discovered_plugin", None))


class TestPluginManagerUnload(unittest.TestCase):
    def _mods_root(self) -> Path:
        root = Path("tmp") / f"plugin_manager_unload_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def setUp(self):
        self.game = MagicMock()
        self.mgr = PluginManager(self.game, mods_dir="unused")

    def test_unload_unknown_plugin_is_a_no_op(self):
        self.mgr.unload_plugin("never_loaded")  # must not raise

    def _load_plugin_with_body(self, plugin_id: str, body: str, root: Path):
        plugin_dir = root / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "manifest.json").write_text(
            json.dumps(dict(VALID_MANIFEST, plugin_id=plugin_id)), encoding="utf-8",
        )
        (plugin_dir / "plugin.py").write_text(body, encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.mgr.load_plugin(str(plugin_dir))
        self.addCleanup(lambda: sys.modules.pop(plugin_id, None))

    def test_unload_without_teardown_removes_registration(self):
        root = self._mods_root()
        self._load_plugin_with_body("no_teardown_plugin", "def setup(api):\n    pass\n", root)
        self.assertIn("no_teardown_plugin", self.mgr.plugins)
        with patch("engine.commands.command_system.unregister_plugin_commands") as mock_unreg:
            self.mgr.unload_plugin("no_teardown_plugin")
        mock_unreg.assert_called_once_with("no_teardown_plugin")
        self.assertNotIn("no_teardown_plugin", self.mgr.plugins)
        self.assertNotIn("no_teardown_plugin", self.mgr.manifests)
        self.assertNotIn("no_teardown_plugin", sys.modules)

    def test_unload_when_module_already_absent_from_sys_modules(self):
        root = self._mods_root()
        self._load_plugin_with_body("already_gone_plugin", "def setup(api):\n    pass\n", root)
        sys.modules.pop("already_gone_plugin", None)
        with patch("engine.commands.command_system.unregister_plugin_commands"):
            self.mgr.unload_plugin("already_gone_plugin")  # must not raise
        self.assertNotIn("already_gone_plugin", self.mgr.plugins)

    def test_unload_calls_teardown_when_present(self):
        root = self._mods_root()
        self._load_plugin_with_body(
            "teardown_plugin",
            "torn_down = []\ndef setup(api):\n    pass\ndef teardown():\n    torn_down.append(True)\n",
            root,
        )
        module = self.mgr.plugins["teardown_plugin"]
        self.mgr.unload_plugin("teardown_plugin")
        self.assertEqual([True], module.torn_down)

    def test_unload_teardown_exception_is_caught_and_logged(self):
        root = self._mods_root()
        self._load_plugin_with_body(
            "bad_teardown_plugin",
            "def setup(api):\n    pass\ndef teardown():\n    raise RuntimeError('teardown boom')\n",
            root,
        )
        with redirect_stdout(io.StringIO()) as out:
            self.mgr.unload_plugin("bad_teardown_plugin")
        self.assertIn("Error during teardown", out.getvalue())
        # Despite the teardown exception, the plugin should still be fully removed.
        self.assertNotIn("bad_teardown_plugin", self.mgr.plugins)


if __name__ == "__main__":
    unittest.main()
