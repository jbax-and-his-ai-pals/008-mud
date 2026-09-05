# tests/singles/test_debug_spawning_commands.py
"""Coverage for GM/debug spawn commands (engine/commands/debug/spawning.py):
`spawn`/`create` and `debuggear`.

Note: spawn_handler's nested `_spawn_item`'s `if not resolved_id:` guard
(line 29) is provably unreachable via the only call site -- the smart-match
dispatcher already calls `_resolve_item_id(name)` and only invokes
`_spawn_item(name, ...)` when that call returned truthy, and a second,
identical call with the same `name` against the same (unchanged)
`world.item_templates` is guaranteed to return the same result. Left
untested as dead code, consistent with this codebase's established
precedent for a redundant guard following an equivalent earlier check."""

from unittest.mock import patch

from tests.fixtures import GameTestBase


class TestSpawnCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("spawn")
        self.assertIn("Usage", result)

    def test_no_match_is_reported(self):
        result = self.game.process_command("spawn totally_not_a_real_thing")
        self.assertIn("No match for", result)

    def test_spawns_item_by_full_id(self):
        before = len(self.world.get_items_in_current_room())
        result = self.game.process_command("spawn item_starter_dagger")
        self.assertIn("Spawned", result)
        self.assertEqual(before + 1, len(self.world.get_items_in_current_room()))

    def test_spawns_item_by_bare_name_with_prefix_resolution(self):
        result = self.game.process_command("spawn starter_dagger")
        self.assertIn("Spawned", result)

    def test_spawns_multiple_items_with_count_suffix(self):
        before = len(self.world.get_items_in_current_room())
        result = self.game.process_command("spawn item_healing_potion_small 3")
        self.assertIn("Spawned", result)
        self.assertEqual(before + 3, len(self.world.get_items_in_current_room()))

    def test_spawn_npc_subcommand_requires_id(self):
        result = self.game.process_command("spawn npc")
        self.assertIn("Usage", result)

    def test_spawn_npc_subcommand_spawns_named_npc(self):
        before = len(self.world.npcs)
        result = self.game.process_command("spawn npc giant_rat")
        self.assertIn("appears", result)
        self.assertEqual(before + 1, len(self.world.npcs))

    def test_spawn_npc_by_bare_template_name(self):
        before = len(self.world.npcs)
        self.game.process_command("spawn giant_rat")
        self.assertEqual(before + 1, len(self.world.npcs))

    def test_spawn_npc_multiple_with_count(self):
        before = len(self.world.npcs)
        self.game.process_command("spawn giant_rat 3")
        self.assertEqual(before + 3, len(self.world.npcs))

    def test_spawn_without_player_location_reports_error(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("spawn item_starter_dagger")
        self.assertIn("Player location unavailable", result)

    def test_item_creation_failure_is_reported(self):
        with patch(
            "engine.commands.debug.spawning.ItemFactory.create_item_from_template", return_value=None,
        ):
            result = self.game.process_command("spawn item_starter_dagger 2")
        self.assertIn("Failed to spawn items", result)

    def test_spawn_npc_without_player_location_reports_error(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("spawn npc giant_rat")
        self.assertIn("Player location unavailable", result)

    def test_npc_creation_failure_is_reported(self):
        with patch(
            "engine.commands.debug.spawning.NPCFactory.create_npc_from_template", return_value=None,
        ):
            result = self.game.process_command("spawn npc giant_rat")
        self.assertIn("Failed to create NPC", result)

    def test_spawn_npc_with_count_and_level_suffix(self):
        before = len(self.world.npcs)
        result = self.game.process_command("spawn giant_rat 3 5")
        self.assertEqual(before + 3, len(self.world.npcs))
        new_npcs = [n for n in self.world.npcs.values() if n.template_id == "giant_rat" and n.level == 5]
        self.assertEqual(3, len(new_npcs))


class TestDebugGearCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        result = self.game.process_command("debuggear")
        self.assertIn("Usage", result)

    def test_on_equips_debug_gear(self):
        result = self.game.process_command("debuggear on")
        self.assertIn("Equipped", result)
        equipped_ids = {i.obj_id for i in self.player.equipment.values() if i}
        self.assertTrue(any(iid.startswith("debug_") for iid in equipped_ids))

    def test_on_twice_reports_gear_already_present(self):
        self.game.process_command("debuggear on")
        result = self.game.process_command("debuggear on")
        self.assertEqual("Gear already present.", result)

    def test_off_removes_debug_gear(self):
        self.game.process_command("debuggear on")
        result = self.game.process_command("debuggear off")
        self.assertEqual("Debug gear removed.", result)
        equipped_ids = {i.obj_id for i in self.player.equipment.values() if i}
        self.assertFalse(any(iid.startswith("debug_") for iid in equipped_ids))

    def test_item_creation_failure_is_skipped(self):
        with patch(
            "engine.commands.debug.spawning.ItemFactory.create_item_from_template", return_value=None,
        ):
            result = self.game.process_command("debuggear on")
        self.assertEqual("Gear already present.", result)
