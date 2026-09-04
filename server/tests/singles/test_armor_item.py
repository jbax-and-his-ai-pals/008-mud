# tests/singles/test_armor_item.py
"""Coverage for engine/items/armor.py: constructor equip_slot normalization
(default/string/list), use()'s equipped-condition-tier reporting and
equip-on-use delegation, and examine()."""

from tests.fixtures import GameTestBase
from engine.items.armor import Armor


class TestArmorConstructor(GameTestBase):
    def test_default_equip_slot_falls_back_to_body(self):
        armor = Armor(obj_id="a1", name="Mystery Armor")
        self.assertEqual(["body"], armor.get_property("equip_slot"))

    def test_string_equip_slot_is_wrapped_in_list(self):
        armor = Armor(obj_id="a2", name="Helm", equip_slot="head")
        self.assertEqual(["head"], armor.get_property("equip_slot"))

    def test_list_equip_slot_is_kept_as_is(self):
        armor = Armor(obj_id="a3", name="Gloves", equip_slot=["hands"])
        self.assertEqual(["hands"], armor.get_property("equip_slot"))

    def test_stackable_kwarg_is_silently_dropped(self):
        armor = Armor(obj_id="a4", name="Plate", stackable=True)
        self.assertFalse(armor.stackable)


class TestArmorUse(GameTestBase):
    def _make_armor(self, obj_id, durability=100, max_durability=100):
        armor = Armor(
            obj_id=obj_id, name="Test Armor", equip_slot=["body"],
            durability=durability,
        )
        armor.properties["max_durability"] = max_durability
        return armor

    def test_equipping_via_use_when_not_equipped(self):
        armor = self._make_armor("armor_equip_test")
        self.player.inventory.add_item(armor)
        result = armor.use(self.player)
        self.assertTrue(any(e is armor for e in self.player.equipment.values()))
        self.assertIn("equip", result.lower())

    def test_checking_condition_when_already_equipped_good(self):
        armor = self._make_armor("armor_good", durability=100, max_durability=100)
        self.player.equipment["body"] = armor
        result = armor.use(self.player)
        self.assertIn("good condition", result)

    def test_checking_condition_slightly_damaged(self):
        armor = self._make_armor("armor_slight", durability=80, max_durability=100)
        self.player.equipment["body"] = armor
        result = armor.use(self.player)
        self.assertIn("slightly damaged", result)

    def test_checking_condition_worn(self):
        armor = self._make_armor("armor_worn", durability=40, max_durability=100)
        self.player.equipment["body"] = armor
        result = armor.use(self.player)
        self.assertIn("worn condition", result)

    def test_checking_condition_almost_broken(self):
        armor = self._make_armor("armor_broken", durability=5, max_durability=100)
        self.player.equipment["body"] = armor
        result = armor.use(self.player)
        self.assertIn("almost broken", result)

    def test_checking_condition_with_zero_max_durability_defaults_good(self):
        armor = self._make_armor("armor_zero_max", durability=0, max_durability=0)
        self.player.equipment["body"] = armor
        result = armor.use(self.player)
        self.assertIn("good condition", result)


class TestArmorExamine(GameTestBase):
    def test_examine_delegates_to_item_examine(self):
        armor = Armor(obj_id="a5", name="Chainmail", description="Rings of steel.")
        result = armor.examine()
        self.assertIn("Chainmail", result)
        self.assertIn("Rings of steel.", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
