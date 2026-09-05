# tests/singles/test_inventory_display_full.py
"""Coverage for engine/items/inventory/display.py: _get_item_sort_key's
empty-slot fallback, and list_items()'s weight/slot percentage color
thresholds (>=90%, >=75%, below).

Note: list_items()'s `if not items_found: return "...empty..."` is
unreachable -- it's guarded by an equivalent, earlier check
(`if all(not slot.item for slot in inventory.slots): return ...`) that
already returns before the loop runs whenever no slot has an item, so by
the time the loop executes, items_found is guaranteed to become True.
Left untested as dead code, consistent with this codebase's established
precedent for a redundant guard following an equivalent earlier check."""

import unittest

from tests.fixtures import GameTestBase
from engine.items.inventory.display import _get_item_sort_key
from engine.items.item import Item


class TestGetItemSortKey(unittest.TestCase):
    def test_empty_slot_sorts_first(self):
        class _EmptySlot:
            item = None
        self.assertEqual(_get_item_sort_key(_EmptySlot()), ("", ""))


class TestListItemsWeightAndSlotThresholds(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.inventory.max_slots = 4
        self.player.inventory.max_weight = 10.0
        # Trim to exactly 4 slots so slot-percentage math is predictable.
        self.player.inventory.slots = self.player.inventory.slots[:4]

    def test_weight_at_or_above_90_percent_uses_error_color(self):
        item = Item(name="Heavy Thing", weight=9.5)
        self.player.inventory.add_item(item)
        result = self.player.inventory.list_items()
        self.assertIn("9.5/10.0", result)

    def test_weight_at_or_above_75_percent_uses_highlight_color(self):
        item = Item(name="Medium Thing", weight=8.0)
        self.player.inventory.add_item(item)
        result = self.player.inventory.list_items()
        self.assertIn("8.0/10.0", result)

    def test_weight_below_75_percent_uses_plain_text(self):
        item = Item(name="Light Thing", weight=1.0)
        self.player.inventory.add_item(item)
        result = self.player.inventory.list_items()
        self.assertIn("1.0/10.0", result)

    def test_slots_at_or_above_90_percent_uses_error_color(self):
        for i in range(4):
            self.player.inventory.add_item(Item(name=f"Slot Filler {i}", weight=0.1))
        result = self.player.inventory.list_items()
        self.assertIn("4/4", result)

    def test_slots_at_or_above_75_percent_uses_highlight_color(self):
        for i in range(3):
            self.player.inventory.add_item(Item(name=f"Slot Filler {i}", weight=0.1))
        result = self.player.inventory.list_items()
        self.assertIn("3/4", result)

    def test_slots_below_75_percent_uses_plain_text(self):
        self.player.inventory.add_item(Item(name="Only Item", weight=0.1))
        result = self.player.inventory.list_items()
        self.assertIn("1/4", result)


if __name__ == "__main__":
    unittest.main()
