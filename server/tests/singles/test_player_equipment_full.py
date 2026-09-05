# tests/singles/test_player_equipment_full.py
"""Coverage for engine/player/equipment.py: get_valid_slots' type-mapping
fallback for a plain Item, equip_item's dead-player/stat-requirement/no-
valid-slots/not-owned/swap-failure/remove-failure branches, and
unequip_item's dead-player/invalid-slot/nothing-equipped/cursed/re-apply-
on-failed-add branches."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item import Item
from engine.items.junk import Junk
from engine.items.weapon import Weapon


class TestGetValidSlots(GameTestBase):
    def test_plain_item_falls_back_to_empty_type_mapping(self):
        item = Item(name="Plain Item", equip_slot=None)
        self.assertEqual(self.player.get_valid_slots(item), [])

    def test_unmapped_type_returns_empty_list(self):
        junk = Junk(name="Bit of Junk", equip_slot=None)
        self.assertEqual(self.player.get_valid_slots(junk), [])

    def test_explicit_slots_with_no_real_match_falls_back_to_type_mapping(self):
        weapon = Weapon(name="Oddly Slotted Sword", damage=5, equip_slot=["not_a_real_slot"])
        self.assertEqual(sorted(self.player.get_valid_slots(weapon)), ["main_hand", "off_hand"])


class TestEquipItem(GameTestBase):
    def _weapon(self, name="Test Sword"):
        weapon = Weapon(name=name, damage=5)
        self.player.inventory.add_item(weapon)
        return weapon

    def test_dead_player_cannot_equip(self):
        weapon = self._weapon()
        self.player.is_alive = False
        ok, msg = self.player.equip_item(weapon)
        self.assertFalse(ok)
        self.assertIn("dead", msg)

    def test_unmet_stat_requirement_is_rejected(self):
        weapon = self._weapon()
        # A satisfied requirement before the failing one exercises the
        # requirements loop's "keep checking" continuation branch too.
        weapon.update_property("requirements", {"strength": 1, "dexterity": 9999})
        ok, msg = self.player.equip_item(weapon)
        self.assertFalse(ok)
        self.assertIn("Dexterity", msg)

    def test_item_with_no_valid_slots_is_rejected(self):
        item = Item(name="Unequippable Thing", equip_slot=None)
        self.player.inventory.add_item(item)
        ok, msg = self.player.equip_item(item)
        self.assertFalse(ok)
        self.assertIn("can't figure out how to equip", msg)

    def test_item_not_in_inventory_is_rejected(self):
        weapon = Weapon(name="Not Owned Sword", damage=5)  # never added to inventory
        ok, msg = self.player.equip_item(weapon)
        self.assertFalse(ok)
        self.assertIn("don't have", msg)

    def test_swap_failure_when_currently_equipped_item_is_cursed(self):
        cursed = self._weapon("Cursed Blade")
        cursed.update_property("cursed", True)
        ok, _ = self.player.equip_item(cursed, slot_name="main_hand")
        self.assertTrue(ok)

        new_weapon = self._weapon("Replacement Sword")
        ok, msg = self.player.equip_item(new_weapon, slot_name="main_hand")
        self.assertFalse(ok)
        self.assertIn("Could not unequip", msg)

    def test_inventory_removal_failure_is_reported(self):
        weapon = self._weapon()
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "mock removal failure")):
            ok, msg = self.player.equip_item(weapon)
        self.assertFalse(ok)
        self.assertIn("Failed to remove", msg)


class TestUnequipItem(GameTestBase):
    def _equip_weapon(self, name="Test Sword"):
        weapon = Weapon(name=name, damage=5)
        self.player.inventory.add_item(weapon)
        ok, _ = self.player.equip_item(weapon, slot_name="main_hand")
        self.assertTrue(ok)
        return weapon

    def test_dead_player_cannot_unequip(self):
        self._equip_weapon()
        self.player.is_alive = False
        ok, msg = self.player.unequip_item("main_hand")
        self.assertFalse(ok)
        self.assertIn("dead", msg)

    def test_invalid_slot_name_is_rejected(self):
        ok, msg = self.player.unequip_item("totally_bogus_slot_xyz")
        self.assertFalse(ok)
        self.assertIn("Invalid equipment slot", msg)

    def test_nothing_equipped_in_slot_is_reported(self):
        ok, msg = self.player.unequip_item("main_hand")
        self.assertFalse(ok)
        self.assertIn("nothing equipped", msg)

    def test_cursed_item_cannot_be_removed(self):
        weapon = self._equip_weapon()
        weapon.update_property("cursed", True)
        ok, msg = self.player.unequip_item("main_hand")
        self.assertFalse(ok)
        self.assertIn("dark curse", msg)

    def test_failed_inventory_add_reapplies_equip_effect(self):
        weapon = self._equip_weapon()
        weapon.update_property("equip_effect", {"name": "Sharpened", "stat_modifiers": {}})
        with patch.object(self.player.inventory, "add_item", return_value=(False, "inventory full")):
            with patch.object(self.player, "apply_effect") as mock_apply:
                ok, msg = self.player.unequip_item("main_hand")
        self.assertFalse(ok)
        self.assertIn("Could not unequip", msg)
        mock_apply.assert_called_once()
        self.assertIs(self.player.equipment["main_hand"], weapon)


if __name__ == "__main__":
    unittest.main()
