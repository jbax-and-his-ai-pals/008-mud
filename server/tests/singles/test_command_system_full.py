# tests/singles/test_command_system_full.py
"""Coverage for engine/commands/command_system.py: unregister_command's
inconsistent-registry and unknown-category branches, unregister_plugin_
commands' empty-id guard and multi-command sweep, content_block_reason's
capability/ruleset rejections, process_input's non-dict-context branch,
get_command_help's category/direction-alias/no-aliases/unknown-name
branches, _get_category_help, and _is_content_enabled's world=None default.

Note: content_block_reason's final fallback return (the literal string
"This command is not available in this game.") and get_help_text's
empty-category-name branches are unreachable given the current logic --
_is_content_enabled's only two failure conditions (missing content_capability,
missing ruleset_system) are the exact same conditions content_block_reason
already checks and returns early for, and get_help_text only iterates
categories that its own filter has already proven contain an enabled
command. They are left untested as dead code, consistent with this
codebase's established precedent for provably-unreachable branches."""

import unittest

from engine.commands.command_system import (
    command,
    get_command_groups,
    registered_commands,
    command_groups,
    unregister_command,
    unregister_plugin_commands,
    CommandProcessor,
)


class _FakeWorld:
    def __init__(self, capabilities=None, ruleset_systems=None):
        self._capabilities = set(capabilities or [])
        self._ruleset_systems = set(ruleset_systems or [])

    def has_capability(self, cap):
        return cap in self._capabilities

    def ruleset_system_enabled(self, name):
        return name in self._ruleset_systems


class TestGetCommandGroups(unittest.TestCase):
    def test_returns_the_shared_command_groups_dict(self):
        self.assertIs(get_command_groups(), command_groups)


class TestUnregisterCommand(unittest.TestCase):
    def test_unknown_command_returns_false(self):
        self.assertFalse(unregister_command("totally_bogus_command_xyz"))

    def test_removes_primary_and_aliases(self):
        # Two aliases so the alias-removal loop actually iterates more than once.
        @command("cmdsys_probe", aliases=["csp", "csp2"], category="other", help_text="probe")
        def _probe(_args, _ctx):
            return "ok"

        self.assertIn("cmdsys_probe", registered_commands)
        self.assertIn("csp", registered_commands)
        self.assertIn("csp2", registered_commands)

        result = unregister_command("cmdsys_probe")

        self.assertTrue(result)
        self.assertNotIn("cmdsys_probe", registered_commands)
        self.assertNotIn("csp", registered_commands)
        self.assertNotIn("csp2", registered_commands)

    def test_inconsistent_registry_entry_skips_primary_deletion(self):
        # Simulate a registry entry reached via a key that doesn't match its
        # own "name" field and was never itself registered as primary --
        # exercises the "if cmd_name in registered_commands" False branch.
        registered_commands["ghost_alias_xyz"] = {
            "name": "ghost_primary_xyz", "aliases": [], "category": "other",
        }
        try:
            result = unregister_command("ghost_alias_xyz")
            self.assertTrue(result)
            self.assertNotIn("ghost_primary_xyz", registered_commands)
        finally:
            registered_commands.pop("ghost_alias_xyz", None)
            registered_commands.pop("ghost_primary_xyz", None)

    def test_alias_not_present_in_registry_is_skipped(self):
        # One real alias (present as its own key) and one phantom alias
        # (listed in aliases but never registered) so the alias-removal
        # loop exercises both the True and False sides of its "if" check.
        cmd_data = {
            "name": "cmdsys_alias_gap_primary",
            "aliases": ["cmdsys_alias_gap_real", "cmdsys_alias_gap_phantom"],
            "category": "other",
        }
        registered_commands["cmdsys_alias_gap_primary"] = cmd_data
        registered_commands["cmdsys_alias_gap_real"] = cmd_data
        try:
            result = unregister_command("cmdsys_alias_gap_primary")
            self.assertTrue(result)
            self.assertNotIn("cmdsys_alias_gap_real", registered_commands)
        finally:
            registered_commands.pop("cmdsys_alias_gap_primary", None)
            registered_commands.pop("cmdsys_alias_gap_real", None)
            registered_commands.pop("cmdsys_alias_gap_phantom", None)

    def test_unknown_category_skips_category_group_cleanup(self):
        registered_commands["ghost_cmd_xyz"] = {
            "name": "ghost_cmd_xyz", "aliases": [], "category": "totally_custom_category_xyz",
        }
        try:
            result = unregister_command("ghost_cmd_xyz")
            self.assertTrue(result)
            self.assertNotIn("ghost_cmd_xyz", registered_commands)
        finally:
            registered_commands.pop("ghost_cmd_xyz", None)


class TestUnregisterPluginCommands(unittest.TestCase):
    def test_empty_plugin_id_returns_zero(self):
        self.assertEqual(unregister_plugin_commands(""), 0)
        self.assertEqual(unregister_plugin_commands(None), 0)

    def test_unregisters_all_commands_for_the_given_plugin(self):
        @command("cmdsys_plugin_a", category="other", help_text="a", plugin_id="cmdsys_test_plugin")
        def _plugin_a(_args, _ctx):
            return "a"

        @command("cmdsys_plugin_b", category="other", help_text="b", plugin_id="cmdsys_test_plugin")
        def _plugin_b(_args, _ctx):
            return "b"

        count = unregister_plugin_commands("cmdsys_test_plugin")

        self.assertEqual(count, 2)
        self.assertNotIn("cmdsys_plugin_a", registered_commands)
        self.assertNotIn("cmdsys_plugin_b", registered_commands)

    def test_entry_whose_name_was_never_actually_registered_is_not_counted(self):
        # A registry entry can report a plugin_id + name without that name
        # itself being a key in registered_commands (e.g. reached only via
        # an alias-style lookup) -- unregister_command then fails for it,
        # exercising the loop's "if unregister_command(...)" False branch.
        registered_commands["cmdsys_phantom_alias"] = {
            "name": "cmdsys_phantom_primary", "aliases": [], "category": "other",
            "plugin_id": "cmdsys_phantom_plugin",
        }
        try:
            count = unregister_plugin_commands("cmdsys_phantom_plugin")
            self.assertEqual(count, 0)
        finally:
            registered_commands.pop("cmdsys_phantom_alias", None)
            registered_commands.pop("cmdsys_phantom_primary", None)


class TestContentBlockReason(unittest.TestCase):
    def setUp(self):
        self.processor = CommandProcessor()

        @command("cmdsys_gated", category="other", help_text="gated",
                 content_capability="cmdsys_fake_capability")
        def _gated(_args, _ctx):
            return "gated"

        @command("cmdsys_ruleset_gated", category="other", help_text="ruleset gated",
                 ruleset_system="cmdsys_fake_ruleset")
        def _ruleset_gated(_args, _ctx):
            return "ruleset gated"

    def tearDown(self):
        unregister_command("cmdsys_gated")
        unregister_command("cmdsys_ruleset_gated")

    def test_no_matching_command_returns_empty_string(self):
        world = _FakeWorld()
        self.assertEqual(self.processor.content_block_reason("totally unknown text", world), "")

    def test_enabled_command_returns_empty_string(self):
        world = _FakeWorld(capabilities={"cmdsys_fake_capability"})
        self.assertEqual(self.processor.content_block_reason("cmdsys_gated", world), "")

    def test_missing_content_capability_returns_reason(self):
        world = _FakeWorld()
        reason = self.processor.content_block_reason("cmdsys_gated", world)
        self.assertIn("cmdsys_fake_capability", reason)

    def test_missing_ruleset_system_returns_reason(self):
        world = _FakeWorld()
        reason = self.processor.content_block_reason("cmdsys_ruleset_gated", world)
        self.assertIn("cmdsys_fake_ruleset", reason)


class TestProcessInputContextHandling(unittest.TestCase):
    def setUp(self):
        self.processor = CommandProcessor()

        @command("cmdsys_echo", category="other", help_text="echo")
        def _echo(_args, _ctx):
            return "echoed"

    def tearDown(self):
        unregister_command("cmdsys_echo")

    def test_dispatches_with_no_context(self):
        result = self.processor.process_input("cmdsys_echo", context=None)
        self.assertEqual(result, "echoed")

    def test_dispatches_with_non_dict_context(self):
        result = self.processor.process_input("cmdsys_echo", context="not a dict")
        self.assertEqual(result, "echoed")

    def test_unknown_command_returns_error_message(self):
        result = self.processor.process_input("totally_bogus_input_xyz")
        self.assertIn("Unknown command", result)


class TestGetCommandHelp(unittest.TestCase):
    def setUp(self):
        self.processor = CommandProcessor()

    def test_category_name_returns_category_help(self):
        result = self.processor.get_command_help("movement", world=None)
        self.assertIn("Movement Commands", result)

    def test_direction_alias_resolves_to_full_command(self):
        result = self.processor.get_command_help("n", world=None)
        self.assertIn("NORTH", result.upper())

    def test_command_with_no_aliases_omits_alias_line(self):
        @command("cmdsys_no_alias", category="other", help_text="solo command")
        def _solo(_args, _ctx):
            return "solo"
        try:
            result = self.processor.get_command_help("cmdsys_no_alias", world=None)
            self.assertNotIn("Aliases:", result)
        finally:
            unregister_command("cmdsys_no_alias")

    def test_unknown_name_returns_fallback_message(self):
        result = self.processor.get_command_help("totally_bogus_xyz", world=None)
        self.assertIn("No help found", result)

    def test_category_help_dedups_a_handler_listed_twice(self):
        # A category group can (in principle) end up listing the same
        # cmd_data twice; _get_category_help must still render it once.
        @command("cmdsys_dup_test", category="other", help_text="dup")
        def _dup(_args, _ctx):
            return "dup"
        try:
            cmd_data = registered_commands["cmdsys_dup_test"]
            command_groups["other"].append(cmd_data)
            result = self.processor.get_command_help("other", world=None)
            self.assertEqual(result.count("cmdsys_dup_test"), 1)
        finally:
            unregister_command("cmdsys_dup_test")


class TestIsContentEnabledDefaultWorld(unittest.TestCase):
    def test_returns_true_when_world_is_none(self):
        self.assertTrue(CommandProcessor._is_content_enabled({"content_capability": "anything"}))


if __name__ == "__main__":
    unittest.main()
