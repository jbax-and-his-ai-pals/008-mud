# tests/singles/test_simple_item_use_methods.py
"""Every item the player can hold answers `use` with something readable.

This used to cover four hardcoded sentences on `Item`, `Gem`, `Junk` and
`Treasure`. Three of those classes are gone: an item's `use_text` is a template
field now, so what is worth asserting is the general contract -- a template with
text says its text, a template without one falls back, and nothing raises.
"""
import unittest

from tests.fixtures import GameTestBase
from engine.items.item import Item


class TestSimpleItemUseMethods(unittest.TestCase):
    def test_base_item_use_reports_no_known_use(self):
        item = Item(name="Rock")
        self.assertIn("don't know how to use", item.use(user=None))

    def test_an_item_with_declared_text_uses_it(self):
        item = Item(name="Golden Crown")
        item.update_property("use_text", "You admire the {name}. It looks quite valuable.")
        self.assertIn("admire", item.use(user=None))

    def test_use_accepts_a_target_without_demanding_one(self):
        """`use_give` calls `use(user=..., target=...)` for some items and not others."""
        item = Item(name="Ruby")
        item.update_property("use_text", "It sparkles brilliantly.")
        self.assertIn("sparkles", item.use(user=None, target=None))


class TestTheShippedItemsAllAnswer(GameTestBase):
    def test_every_item_the_player_can_pick_up_can_be_used_without_raising(self):
        """A `use` that raises is a command failure the player sees as an error."""
        checked = 0
        for template_id in sorted(self.world.item_templates):
            from engine.items.item_factory import ItemFactory

            item = ItemFactory.create_item_from_template(template_id, self.world)
            if item is None:
                continue
            checked += 1
            text = item.use(user=self.player)
            self.assertIsInstance(text, str, template_id)
            self.assertTrue(text.strip(), template_id)
        self.assertGreater(checked, 200, "the shipped set should have plenty of items")


if __name__ == "__main__":
    unittest.main()
