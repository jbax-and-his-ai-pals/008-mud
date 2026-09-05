# tests/singles/test_simple_item_use_methods.py
"""Coverage for the trivial use() flavor-text methods on Item, Gem, Junk,
and Treasure -- none of which are exercised by any existing test."""

import unittest

from engine.items.item import Item
from engine.items.gem import Gem
from engine.items.junk import Junk
from engine.items.treasure import Treasure


class TestSimpleItemUseMethods(unittest.TestCase):
    def test_base_item_use_reports_no_known_use(self):
        item = Item(name="Rock")
        self.assertIn("don't know how to use", item.use(user=None))

    def test_gem_use_sparkles(self):
        gem = Gem(name="Ruby")
        self.assertIn("sparkles", gem.use(user=None))

    def test_junk_use_no_immediate_use(self):
        junk = Junk(name="Broken Widget")
        self.assertIn("can't find any immediate use", junk.use(user=None))

    def test_treasure_use_admire(self):
        treasure = Treasure(name="Golden Crown")
        self.assertIn("admire", treasure.use(user=None))


if __name__ == "__main__":
    unittest.main()
