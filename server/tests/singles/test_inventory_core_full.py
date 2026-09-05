# tests/singles/test_inventory_core_full.py
"""Coverage for engine/items/inventory/core.py's Inventory: defensive
branches around corrupted/inconsistent slot state that the happy-path
add/remove tests elsewhere never construct.

Note: two branches are left untested as unreachable given the codebase's
non-negative-quantity invariant (a slot's quantity is only ever changed via
InventorySlot.add()/remove(), which always keep it >= 0):
- remove_item()'s for-loop-exhausts-without-a-break arc (the reversed slot
  scan running past every slot without ever satisfying
  `actual_removed_count >= quantity_to_remove`) requires the accumulated
  total to fall short of `quantity_to_remove`, but that value is computed
  as `min(total_available, quantity)` where `total_available` is the exact
  sum of every matching slot's own quantity -- accumulating across every
  matching slot the scan visits is guaranteed to reach it.
- remove_item()'s `total_available == 0` branch succeeding via
  remove_item_instance() (rather than falling through to "Failed to
  remove...") requires a slot with a *negative* quantity elsewhere
  canceling out a positive one, since a lone zero-quantity slot (the only
  non-negative way to reach `total_available == 0` while still being
  findable) can never itself report a removed count of 1."""

import unittest

from engine.items.inventory.core import Inventory
from engine.items.item import Item


class TestAddItemWithStackableFlagMismatch(unittest.TestCase):
    """A slot can (in principle, e.g. via a hand-edited or corrupted save
    file deserialized through InventorySlot.from_dict) hold an item whose
    own `stackable` flag disagrees with an incoming item sharing its
    obj_id. can_add_item's pre-check only looks at the incoming item's
    flag, so it can green-light a stack merge that slot.add() then
    silently refuses (it checks the *stored* item's flag) -- these tests
    exercise that mismatch."""

    def test_mismatched_stack_falls_through_to_an_empty_slot(self):
        inv = Inventory(max_slots=5)
        stuck_item = Item(obj_id="dup_id", name="Stuck", stackable=False)
        inv.slots[0].item = stuck_item
        inv.slots[0].quantity = 1

        incoming = Item(obj_id="dup_id", name="Stuck", stackable=True)
        success, message = inv.add_item(incoming, 3)

        self.assertTrue(success)
        self.assertEqual(3, inv.slots[1].quantity)

    def test_mismatched_stack_with_no_empty_slots_reports_no_space(self):
        inv = Inventory(max_slots=2)
        stuck_item = Item(obj_id="dup_id2", name="Stuck", stackable=False)
        inv.slots[0].item = stuck_item
        inv.slots[0].quantity = 1
        filler = Item(obj_id="filler", name="Filler", stackable=False)
        inv.slots[1].item = filler
        inv.slots[1].quantity = 1

        incoming = Item(obj_id="dup_id2", name="Stuck", stackable=True)
        success, message = inv.add_item(incoming, 1)

        self.assertFalse(success)
        self.assertIn("Not enough space", message)


class TestRemoveItemWithCorruptedZeroQuantitySlot(unittest.TestCase):
    """A slot holding an item with quantity 0 (reachable via a corrupted
    save's InventorySlot.from_dict) makes total_available undercount what
    find_item_by_id can still see."""

    def test_only_a_zero_quantity_slot_present_fails_to_remove(self):
        inv = Inventory(max_slots=3)
        ghost = Item(obj_id="ghost_item", name="Ghost", stackable=True)
        inv.slots[0].item = ghost
        inv.slots[0].quantity = 0

        instance, count, message = inv.remove_item("ghost_item", 1)

        self.assertIsNone(instance)
        self.assertEqual(0, count)
        self.assertIn("Failed to remove specific instance", message)

    def test_zero_quantity_slot_among_matching_slots_is_skipped_during_removal(self):
        inv = Inventory(max_slots=3)
        corrupted = Item(obj_id="mixed", name="Mixed", stackable=True)
        inv.slots[1].item = corrupted
        inv.slots[1].quantity = 0
        real = Item(obj_id="mixed", name="Mixed", stackable=True)
        inv.slots[0].item = real
        inv.slots[0].quantity = 1

        instance, count, message = inv.remove_item("mixed", 1)

        self.assertIs(real, instance)
        self.assertEqual(1, count)


class TestRemoveItemRequestingZeroQuantity(unittest.TestCase):
    def test_requesting_zero_quantity_removes_nothing(self):
        # A single-slot inventory so the first (and only) slot the reversed
        # scan visits is itself a match, hitting the
        # `actual_removed_count < quantity_to_remove` False branch for a
        # matching slot rather than short-circuiting on an empty one.
        inv = Inventory(max_slots=1)
        item = Item(obj_id="some_item", name="Something", stackable=True)
        inv.slots[0].item = item
        inv.slots[0].quantity = 5

        instance, count, message = inv.remove_item("some_item", 0)

        self.assertIsNone(instance)
        self.assertEqual(0, count)
        self.assertEqual(5, inv.slots[0].quantity)


class TestRemoveItemInstance(unittest.TestCase):
    def test_none_instance_returns_false(self):
        inv = Inventory(max_slots=1)
        self.assertFalse(inv.remove_item_instance(None))

    def test_instance_not_present_returns_false(self):
        inv = Inventory(max_slots=1)
        stray = Item(obj_id="not_here", name="Stray")
        self.assertFalse(inv.remove_item_instance(stray))


if __name__ == "__main__":
    unittest.main()
