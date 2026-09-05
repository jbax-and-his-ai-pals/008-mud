# tests/singles/test_inventory_persistence_full.py
"""Coverage for engine/items/inventory/persistence.py: from_dict()'s
no-world fallback, falsy/malformed slot-data skip, non-stackable-with-
quantity-over-one warning, failed item creation, and slot-count padding/
truncation to match max_slots."""

import io
import unittest
from contextlib import redirect_stdout

from tests.fixtures import GameTestBase
from engine.items.inventory.core import Inventory


class TestFromDictNoWorld(unittest.TestCase):
    def test_missing_world_returns_bare_inventory_with_requested_dimensions(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            inventory = Inventory.from_dict({"max_slots": 5, "max_weight": 50.0}, None)
        self.assertEqual(inventory.max_slots, 5)
        self.assertEqual(inventory.max_weight, 50.0)
        self.assertIn("World context required", buf.getvalue())


class TestFromDictSlotHandling(GameTestBase):
    def test_falsy_and_malformed_slot_entries_become_empty_slots(self):
        data = {
            "max_slots": 3, "max_weight": 100.0,
            "slots": [None, "not a dict", {"no_item_id_here": True}],
        }
        inventory = Inventory.from_dict(data, self.world)
        self.assertTrue(all(slot.item is None for slot in inventory.slots))

    def test_non_stackable_item_with_quantity_over_one_is_clamped_to_one(self):
        data = {
            "max_slots": 5, "max_weight": 100.0,
            "slots": [{"item_id": "item_iron_sword", "quantity": 5}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            inventory = Inventory.from_dict(data, self.world)
        self.assertEqual(inventory.slots[0].quantity, 1)
        self.assertIn("Set to 1", buf.getvalue())

    def test_stackable_item_keeps_its_saved_quantity(self):
        data = {
            "max_slots": 5, "max_weight": 100.0,
            "slots": [{"item_id": "item_healing_potion_small", "quantity": 3}],
        }
        inventory = Inventory.from_dict(data, self.world)
        self.assertEqual(inventory.slots[0].quantity, 3)

    def test_failed_item_creation_becomes_an_empty_slot(self):
        data = {
            "max_slots": 3, "max_weight": 100.0,
            "slots": [{"item_id": "totally_bogus_item_template_xyz"}],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            inventory = Inventory.from_dict(data, self.world)
        self.assertIsNone(inventory.slots[0].item)
        self.assertIn("Failed to load item", buf.getvalue())

    def test_fewer_saved_slots_than_max_slots_pads_with_empty_slots(self):
        data = {
            "max_slots": 5, "max_weight": 100.0,
            "slots": [{"item_id": "item_iron_sword"}],
        }
        inventory = Inventory.from_dict(data, self.world)
        self.assertEqual(len(inventory.slots), 5)

    def test_more_saved_slots_than_max_slots_truncates(self):
        data = {
            "max_slots": 2, "max_weight": 100.0,
            "slots": [None, None, None, None],
        }
        inventory = Inventory.from_dict(data, self.world)
        self.assertEqual(len(inventory.slots), 2)


if __name__ == "__main__":
    unittest.main()
