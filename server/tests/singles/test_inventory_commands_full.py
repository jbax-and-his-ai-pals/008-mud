# tests/singles/test_inventory_commands_full.py
"""Coverage for engine/commands/inventory.py's guard clauses and the
entirely-untested unequip command: invmode's mode-setting/invalid-mode
branches, status/equip's no-player guards, equip's dead-player guard and
'to <slot>' preposition parsing, and unequip's no-args listing,
slot-name-direct, exact/partial item-name matching, ambiguous-match, and
not-found paths.

Note: equip_handler's `except ValueError:` around
`.index(EQUIP_COMMAND_SLOT_PREPOSITION)` is unreachable -- the preceding
`if EQUIP_COMMAND_SLOT_PREPOSITION in [...]` check already guarantees the
value is present, so `.index()` can never raise. Left untested as dead
code, consistent with this codebase's established precedent (e.g.
engine/commands/magic.py's cast_handler has the identical pattern)."""

from tests.fixtures import GameTestBase
from engine.items.weapon import Weapon


class TestInventoryHandlerGuard(GameTestBase):
    def test_no_player_direct_call(self):
        from engine.commands.inventory import inventory_handler
        result = inventory_handler([], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)


class TestInvmodeHandler(GameTestBase):
    def test_no_args_reports_current_mode(self):
        result = self.game.process_command("invmode")
        self.assertIn("Current mode", result)

    def test_valid_mode_text(self):
        result = self.game.process_command("invmode text")
        self.assertIn("set to text", result)
        self.assertEqual("text", self.game.inventory_mode)

    def test_valid_mode_icon(self):
        result = self.game.process_command("invmode icon")
        self.assertIn("set to icon", result)

    def test_valid_mode_hybrid(self):
        result = self.game.process_command("invmode hybrid")
        self.assertIn("set to hybrid", result)

    def test_invalid_mode_reports_error(self):
        result = self.game.process_command("invmode nonsense")
        self.assertIn("Invalid mode", result)


class TestStatusHandlerGuard(GameTestBase):
    def test_no_player_direct_call(self):
        from engine.commands.inventory import status_handler
        result = status_handler([], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)


class TestEquipHandlerGuards(GameTestBase):
    def test_dead_player_cannot_equip(self):
        # process_command's own dead-player allowlist intercepts most
        # commands before dispatch, so call the handler directly to reach
        # its own internal is_alive guard.
        from engine.commands.inventory import equip_handler
        self.player.is_alive = False
        result = equip_handler(["dagger"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_prompts(self):
        result = self.game.process_command("equip")
        self.assertIn("What do you want to equip", result)

    def test_unknown_item_reports_not_in_inventory(self):
        result = self.game.process_command("equip a_totally_unowned_item")
        self.assertIn("don't have", result)

    def test_equip_with_to_slot_preposition(self):
        weapon = Weapon(obj_id="equip_test_sword", name="Test Sword")
        self.player.inventory.add_item(weapon)
        result = self.game.process_command("equip test sword to main_hand")
        self.assertIn("Test Sword", result)
        self.assertIs(weapon, self.player.equipment.get("main_hand"))

    def test_equip_without_to_preposition_uses_default_slot(self):
        weapon = Weapon(obj_id="equip_test_sword2", name="Plain Sword")
        self.player.inventory.add_item(weapon)
        result = self.game.process_command("equip plain sword")
        self.assertTrue(any(e is weapon for e in self.player.equipment.values()))


class TestUnequipHandler(GameTestBase):
    def test_no_player_direct_call(self):
        from engine.commands.inventory import unequip_handler
        self.world.player = None
        result = unequip_handler([], {"world": self.world})
        self.assertIn("must start or load a game", result)

    def test_dead_player_cannot_unequip(self):
        from engine.commands.inventory import unequip_handler
        self.player.is_alive = False
        result = unequip_handler(["main_hand"], {"world": self.world, "player": self.player})
        self.assertIn("You are dead", result)

    def test_no_args_with_nothing_equipped_lists_empty(self):
        for slot in self.player.equipment:
            self.player.equipment[slot] = None
        result = self.game.process_command("unequip")
        self.assertIn("Nothing equipped", result)
        self.assertIn("Usage: unequip", result)

    def test_no_args_lists_equipped_items(self):
        weapon = Weapon(obj_id="unequip_list_sword", name="Listed Sword")
        self.player.equipment["main_hand"] = weapon
        result = self.game.process_command("unequip")
        self.assertIn("Listed Sword", result)
        self.assertIn("Main hand", result)

    def test_unequip_by_slot_name_directly(self):
        weapon = Weapon(obj_id="unequip_by_slot", name="Slotted Sword")
        self.player.equipment["main_hand"] = weapon
        result = self.game.process_command("unequip main_hand")
        self.assertIsNone(self.player.equipment["main_hand"])

    def test_unequip_by_exact_item_name(self):
        weapon = Weapon(obj_id="unequip_exact", name="Rusty Blade")
        self.player.equipment["main_hand"] = weapon
        result = self.game.process_command("unequip rusty blade")
        self.assertIsNone(self.player.equipment["main_hand"])

    def test_unequip_by_partial_item_name(self):
        weapon = Weapon(obj_id="unequip_partial", name="Ancient Rusty Blade")
        self.player.equipment["main_hand"] = weapon
        result = self.game.process_command("unequip rusty")
        self.assertIsNone(self.player.equipment["main_hand"])

    def test_unequip_by_name_skips_non_matching_equipped_items(self):
        decoy = Weapon(obj_id="unequip_decoy", name="Totally Different Item")
        target = Weapon(obj_id="unequip_target", name="Findable Blade")
        self.player.equipment["main_hand"] = decoy
        self.player.equipment["off_hand"] = target
        result = self.game.process_command("unequip findable blade")
        self.assertIsNone(self.player.equipment["off_hand"])
        self.assertIs(decoy, self.player.equipment["main_hand"])

    def test_unequip_no_match_reports_error(self):
        result = self.game.process_command("unequip nonexistent_item_xyz")
        self.assertIn("don't have an item called", result)

    def test_unequip_ambiguous_match_reports_error(self):
        sword_a = Weapon(obj_id="ambig_a", name="Iron Sword")
        sword_b = Weapon(obj_id="ambig_b", name="Iron Dagger")
        self.player.equipment["main_hand"] = sword_a
        self.player.equipment["off_hand"] = sword_b
        result = self.game.process_command("unequip iron")
        self.assertIn("multiple items", result)
        self.assertIn("Iron Sword", result)
        self.assertIn("Iron Dagger", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
