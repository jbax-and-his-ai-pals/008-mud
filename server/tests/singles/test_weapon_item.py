# tests/singles/test_weapon_item.py
"""Coverage for engine/items/weapon.py: constructor equip_slot default,
use()'s equipped-condition/broken reporting and equip-on-use delegation,
and examine()."""

from tests.fixtures import GameTestBase
from engine.items.weapon import Weapon


class TestWeaponConstructor(GameTestBase):
    def test_default_equip_slot_is_both_hands(self):
        weapon = Weapon(obj_id="w1", name="Fists")
        self.assertEqual(["main_hand", "off_hand"], weapon.get_property("equip_slot"))

    def test_explicit_equip_slot_is_kept(self):
        weapon = Weapon(obj_id="w2", name="Dagger", equip_slot=["main_hand"])
        self.assertEqual(["main_hand"], weapon.get_property("equip_slot"))

    def test_stackable_kwarg_is_silently_dropped(self):
        weapon = Weapon(obj_id="w3", name="Sword", stackable=True)
        self.assertFalse(weapon.stackable)


class TestWeaponUse(GameTestBase):
    def _make_weapon(self, obj_id, durability=100, max_durability=100):
        weapon = Weapon(obj_id=obj_id, name="Test Blade", durability=durability)
        weapon.properties["max_durability"] = max_durability
        return weapon

    def test_equipping_via_use_when_not_equipped(self):
        weapon = self._make_weapon("weapon_equip_test")
        self.player.inventory.add_item(weapon)
        result = weapon.use(self.player)
        self.assertTrue(any(e is weapon for e in self.player.equipment.values()))
        self.assertIn("equip", result.lower())

    def test_broken_weapon_cannot_be_used(self):
        weapon = self._make_weapon("weapon_broken", durability=0, max_durability=100)
        self.player.equipment["main_hand"] = weapon
        result = weapon.use(self.player)
        self.assertIn("broken and cannot be used", result)

    def test_sturdy_condition_above_half_durability(self):
        weapon = self._make_weapon("weapon_sturdy", durability=80, max_durability=100)
        self.player.equipment["main_hand"] = weapon
        result = weapon.use(self.player)
        self.assertIn("sturdy", result)

    def test_worn_condition_at_or_below_half_durability(self):
        weapon = self._make_weapon("weapon_worn", durability=40, max_durability=100)
        self.player.equipment["main_hand"] = weapon
        result = weapon.use(self.player)
        self.assertIn("worn", result)


class TestWeaponExamine(GameTestBase):
    def test_examine_delegates_to_item_examine(self):
        weapon = Weapon(obj_id="w4", name="Longsword", description="A fine blade.")
        result = weapon.examine()
        self.assertIn("Longsword", result)
        self.assertIn("A fine blade.", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
