# tests/singles/test_debug_state_commands.py
"""Coverage for GM/debug player-state commands
(engine/commands/debug/state.py): sethealth, setgold, level,
applyeffect, removeeffect."""

from tests.fixtures import GameTestBase


class TestSetHealthCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertIn("Usage", self.game.process_command("sethealth"))

    def test_invalid_number_is_reported(self):
        self.assertEqual("Invalid number.", self.game.process_command("sethealth abc"))

    def test_sets_health_within_bounds(self):
        result = self.game.process_command("sethealth 5")
        self.assertIn("Health set to 5", result)
        self.assertEqual(5, self.player.health)

    def test_clamps_to_max_health(self):
        self.game.process_command(f"sethealth {self.player.max_health + 1000}")
        self.assertEqual(self.player.max_health, self.player.health)

    def test_clamps_negative_to_zero_and_kills_player(self):
        result = self.game.process_command("sethealth -50")
        self.assertIn("Health set to 0", result)
        self.assertFalse(self.player.is_alive)


class TestSetGoldCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertIn("Usage", self.game.process_command("setgold"))

    def test_invalid_number_is_reported(self):
        self.assertEqual("Invalid number.", self.game.process_command("setgold abc"))

    def test_negative_amount_is_rejected(self):
        result = self.game.process_command("setgold -5")
        self.assertIn("cannot be negative", result)

    def test_sets_gold(self):
        result = self.game.process_command("setgold 500")
        self.assertIn("Gold set to 500", result)
        self.assertEqual(500, self.player.runtime_state.gold)


class TestLevelCommand(GameTestBase):
    def test_no_player_reports_not_found(self):
        from engine.commands.debug.state import level_command_handler
        result = level_command_handler([], {"player": None})
        self.assertIn("Player not found", result)

    def test_levels_up_once_by_default(self):
        start_level = self.player.runtime_state.progression.level
        self.game.process_command("level")
        self.assertEqual(start_level + 1, self.player.runtime_state.progression.level)

    def test_levels_up_multiple_times(self):
        start_level = self.player.runtime_state.progression.level
        self.game.process_command("level 3")
        self.assertEqual(start_level + 3, self.player.runtime_state.progression.level)


class TestApplyAndRemoveEffectCommands(GameTestBase):
    def test_applyeffect_missing_args_lists_available_effects(self):
        result = self.game.process_command("applyeffect")
        self.assertIn("Available:", result)
        self.assertIn("debug_poison", result)

    def test_applyeffect_unknown_target_is_reported(self):
        result = self.game.process_command("applyeffect nobody_here debug_poison")
        self.assertEqual("Target not found.", result)

    def test_applyeffect_unknown_effect_is_reported(self):
        result = self.game.process_command("applyeffect self not_a_real_effect")
        self.assertEqual("Effect not found.", result)

    def test_applyeffect_on_self(self):
        result = self.game.process_command("applyeffect self debug_poison")
        self.assertIn("Applied debug_poison", result)
        self.assertTrue(self.player.has_effect("Debug Poison"))

    def test_applyeffect_on_npc_target(self):
        # applyeffect only reads args[0] as the target, so it only supports
        # single-word target names (matching its own "ae <target> <effect>" usage).
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template(
            "village_elder", self.world, instance_id="effect_target", name="Targetnpc"
        )
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        self.world.add_npc(npc)

        result = self.game.process_command("applyeffect Targetnpc debug_poison")
        self.assertIn("Applied", result)
        self.assertTrue(npc.has_effect("Debug Poison"))

    def test_removeeffect_missing_args_shows_usage(self):
        self.assertIn("Usage", self.game.process_command("removeeffect"))

    def test_removeeffect_unknown_target_is_reported(self):
        result = self.game.process_command("removeeffect nobody_here debug_poison")
        self.assertEqual("Target not found.", result)

    def test_removeeffect_not_present_is_reported(self):
        result = self.game.process_command("removeeffect self debug_poison")
        self.assertEqual("Effect not found.", result)

    def test_removeeffect_unknown_effect_name_is_reported(self):
        result = self.game.process_command("removeeffect self not_a_real_effect")
        self.assertEqual("Effect not found.", result)

    def test_removeeffect_removes_applied_effect(self):
        self.game.process_command("applyeffect self debug_poison")
        result = self.game.process_command("removeeffect self debug_poison")
        self.assertIn("Removed", result)
        self.assertFalse(self.player.has_effect("Debug Poison"))
