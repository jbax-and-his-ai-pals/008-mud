# tests/singles/test_inventory_slot_full.py
"""Coverage for engine/items/inventory/slot.py: add()'s cannot-add
fallback (occupied slot, mismatched/non-stackable item), remove()'s
empty-slot guard, to_dict(), and from_dict()."""

import unittest

from tests.fixtures import GameTestBase
from engine.items.inventory.slot import InventorySlot
from engine.items.item import Item
from engine.items.item_factory import ItemFactory


class TestSlotAdd(unittest.TestCase):
    def test_cannot_add_mismatched_item_to_occupied_slot(self):
        item_a = Item(name="Item A")
        item_a.stackable = True
        item_b = Item(name="Item B")
        item_b.stackable = True
        slot = InventorySlot(item_a, 1)
        result = slot.add(item_b, 1)
        self.assertEqual(result, 0)


class TestSlotRemove(unittest.TestCase):
    def test_remove_from_empty_slot_returns_none_and_zero(self):
        slot = InventorySlot()
        result = slot.remove(1)
        self.assertEqual(result, (None, 0))


class TestSlotSerialization(GameTestBase):
    def test_to_dict_with_item(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        slot = InventorySlot(item, 1)
        data = slot.to_dict()
        self.assertEqual(data["quantity"], 1)
        self.assertIsNotNone(data["item"])

    def test_to_dict_without_item(self):
        slot = InventorySlot()
        data = slot.to_dict()
        self.assertIsNone(data["item"])
        self.assertEqual(data["quantity"], 0)

    def test_from_dict_with_item(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        original_slot = InventorySlot(item, 1)
        data = original_slot.to_dict()
        restored = InventorySlot.from_dict(data)
        self.assertIsNotNone(restored.item)
        self.assertEqual(restored.quantity, 1)

    def test_from_dict_without_item(self):
        restored = InventorySlot.from_dict({"item": None, "quantity": 0})
        self.assertIsNone(restored.item)
        self.assertEqual(restored.quantity, 0)


if __name__ == "__main__":
    unittest.main()
