# tests/singles/test_item_use_text.py
"""Flavour text an item declares, instead of a class that exists to hold it.

`Gem`, `Junk` and `Treasure` were three `Item` subclasses whose whole content was
a sentence, a `stackable` default and (for gems) a hardcoded `gift_tags:
["gem"]`. Three engine classes for three strings, and a content set could change
none of them: a sci-fi set could not retag its salvage as salvage, and an author
could not reword one curio without an engine change.

The behaviour is the same; the source of it is now the template. That is the test
this file cares about most: the *same* sentences, the *same* stackability, and
the same gift tag, with no class to hardcode them.
"""
import json
import unittest
from pathlib import Path

from tests.fixtures import GameTestBase
from engine.items.item import Item
from engine.items.item_factory import ITEM_CLASS_MAP, ItemFactory


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")


class TestTheBaseItemReadsItsTemplate(unittest.TestCase):
    def test_an_item_with_no_declared_text_says_it_has_no_known_use(self):
        self.assertIn("don't know how to use", Item(name="Rock").use(user=None))

    def test_declared_text_is_what_the_player_reads(self):
        item = Item(name="Ruby")
        item.update_property("use_text", "You hold the {name} up to the light.")
        self.assertEqual("You hold the Ruby up to the light.", item.use(user=None))

    def test_the_placeholder_accepts_either_spelling(self):
        item = Item(name="Ruby")
        item.update_property("use_text", "{item_name}, again.")
        self.assertEqual("Ruby, again.", item.use(user=None))

    def test_a_brace_that_is_not_a_placeholder_does_not_lose_the_sentence(self):
        """Authored prose is not a format string; a stray brace is still prose."""
        item = Item(name="Ruby")
        item.update_property("use_text", "You weigh the {name} in your palm {hmm}.")
        self.assertIn("You weigh the Ruby in your palm", item.use(user=None))

    def test_empty_or_blank_text_falls_back_rather_than_printing_nothing(self):
        item = Item(name="Ruby")
        item.update_property("use_text", "   ")
        self.assertIn("don't know how to use", item.use(user=None))


class TestTheClassesAreGone(unittest.TestCase):
    def test_the_engine_has_no_gem_junk_or_treasure_class(self):
        for module in ("gem", "junk", "treasure"):
            self.assertFalse(
                (REPO_ROOT / "server" / "engine" / "items" / ("%s.py" % module)).exists(),
                "%s.py still exists" % module,
            )

    def test_the_old_type_names_still_resolve_to_an_item(self):
        """A content set that still writes the old word keeps working."""
        for legacy_type in ("Gem", "Junk", "Treasure"):
            self.assertIs(Item, ITEM_CLASS_MAP[legacy_type])

    def test_a_mechanic_is_still_a_class(self):
        """The line that matters: classes are for behaviour, not for defaults."""
        for mechanic in ("Container", "Key", "Weapon", "Armor", "Consumable", "Lockpick"):
            self.assertIn(mechanic, ITEM_CLASS_MAP)
            self.assertIsNot(Item, ITEM_CLASS_MAP[mechanic])


class TestTheShippedTemplatesCarryTheDefaults(GameTestBase):
    """Everything the classes used to supply, the templates now say."""

    def _templates_of_type(self, content_type: str):
        for template_id, template in self.world.item_templates.items():
            if isinstance(template, dict) and template.get("type") == content_type:
                yield template_id, template

    def test_every_gem_is_stackable_and_tagged(self):
        gems = list(self._templates_of_type("Gem"))
        self.assertTrue(gems, "the fantasy set declares gems")
        for template_id, template in gems:
            self.assertIs(True, template.get("stackable"), template_id)
            self.assertEqual(["gem"], template.get("gift_tags"), template_id)
            self.assertIn("{name}", str(template.get("use_text", "")), template_id)

    def test_a_gem_built_from_its_template_behaves_as_before(self):
        item = ItemFactory.create_item_from_template("item_quartz_crystal", self.world)
        self.assertIsNotNone(item)
        self.assertTrue(item.stackable)
        self.assertEqual(["gem"], item.get_property("gift_tags"))
        self.assertIn("sparkles", item.use(user=None))
        self.assertIn("quartz crystal", item.use(user=None))

    def test_a_junk_template_reads_its_own_sentence(self):
        item = ItemFactory.create_item_from_template("item_scrap", self.world)
        self.assertIsNotNone(item)
        self.assertIn("can't find any immediate use", item.use(user=None))

    def test_a_treasure_template_reads_its_own_sentence(self):
        item = ItemFactory.create_item_from_template("item_lost_earring", self.world)
        self.assertIsNotNone(item)
        self.assertIn("admire", item.use(user=None))

    def test_no_template_of_these_types_is_left_without_use_text(self):
        """The migration is finished, so nothing relies on a class default."""
        missing = []
        for content_type in ("Gem", "Junk", "Treasure"):
            for template_id, template in self._templates_of_type(content_type):
                if not str(template.get("use_text", "")).strip():
                    missing.append(template_id)
        self.assertEqual([], missing)

    def test_the_declared_gift_tag_is_one_a_gift_rule_can_read(self):
        """A tag nobody can prefer is a tag that does nothing."""
        declared: set = set()
        for path in sorted((REPO_ROOT / "content_sets" / "fantasy_frontier" / "data").rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            def walk(node):
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key in ("preferred_gift_tags", "disliked_gift_tags") and isinstance(value, list):
                            declared.update(str(tag) for tag in value)
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)

            walk(payload)
        self.assertIn("gem", declared)


if __name__ == "__main__":
    unittest.main()
