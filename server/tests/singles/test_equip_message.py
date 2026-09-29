# tests/singles/test_equip_message.py
"""Equipping says what you did, and only says where when where is worth saying.

"You equip the dark armor in your body." reads oddly: nobody equips armour "in" their body. The
body slot is now unsaid ("You equip the dark armor."), and the other slots use the preposition a
person would ("on your head", "in your main hand").
"""

import unittest

from engine.items.item_factory import ItemFactory
from engine.player.equipment import _where_worn
from tests.fixtures import GameTestBase


class TestEquipMessage(GameTestBase):
    def test_body_armour_does_not_name_the_slot(self):
        for item_id in sorted(self.world.item_templates):
            item = ItemFactory.create_item_from_template(item_id, self.world)
            if item is not None and "body" in self.player.get_valid_slots(item):
                self.player.inventory.add_item(item)
                ok, message = self.player.equip_item(item, "body")
                self.assertTrue(ok, message)
                self.assertEqual("You equip the %s." % item.name, message.split(") ")[-1])
                return
        self.skipTest("no item in this set fits the body slot")

    def test_a_worn_phrase_reads_naturally_for_each_slot(self):
        self.assertEqual("", _where_worn("body"))
        self.assertEqual(" in your main hand", _where_worn("main_hand"))
        self.assertEqual(" on your head", _where_worn("head"))
        self.assertEqual(" on your feet", _where_worn("feet"))
        self.assertEqual(" around your neck", _where_worn("neck"))
        self.assertEqual(" in your tail", _where_worn("tail"), "a slot a content set adds still reads")


if __name__ == "__main__":
    unittest.main()
