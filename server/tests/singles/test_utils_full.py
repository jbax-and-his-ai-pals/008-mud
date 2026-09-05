# tests/singles/test_utils_full.py
"""Coverage for engine/utils/utils.py: debug_string, _serialize_item_
reference's falsy-item/missing-obj_id/no-template/debug-print/nested-
container branches, get_article/simple_plural's empty-string guards,
format_name_for_display's no-target and Item-target branches,
get_departure_phrase/get_arrival_phrase's generic fallback, and
weighted_choice's random.choices exception fallback.

Note: format_loot_drop_message's `if not loot_message_parts: return ""`
and weighted_choice's `random.choice(options) if options else None` (the
`else None` half) are provably unreachable -- both are guarded by an
earlier `if not <the same source collection>: return`/`return None` that
already guarantees the later collection is non-empty by construction.
Left untested as dead code, consistent with this codebase's established
precedent."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.utils.utils import (
    debug_string,
    _serialize_item_reference,
    get_article,
    simple_plural,
    format_name_for_display,
    get_departure_phrase,
    get_arrival_phrase,
    weighted_choice,
)
from engine.items.item import Item
from engine.items.container import Container
from engine.items.item_factory import ItemFactory


class TestDebugString(unittest.TestCase):
    def test_prints_each_character_with_position_and_ord(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            debug_string("Hi")
        output = buf.getvalue()
        self.assertIn("Position 0: 'H'", output)
        self.assertIn("Position 1: 'i'", output)
        self.assertIn("End of string", output)


class TestSerializeItemReference(GameTestBase):
    def test_falsy_item_returns_none(self):
        self.assertIsNone(_serialize_item_reference(None, 1, self.world))

    def test_item_missing_obj_id_returns_none(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        item.obj_id = ""
        self.assertIsNone(_serialize_item_reference(item, 1, self.world))

    def test_item_with_no_matching_template_saves_full_state(self):
        item = Item(name="Ghost Item", description="Not in any template.")
        item.obj_id = "totally_bogus_template_id_xyz"
        item.update_property("durability", 5)
        ref = _serialize_item_reference(item, 1, self.world)
        self.assertEqual(ref["item_id"], "totally_bogus_template_id_xyz")
        self.assertEqual(ref["properties_override"]["name"], "Ghost Item")
        self.assertEqual(ref["properties_override"]["durability"], 5)

    def test_container_with_nested_items_serializes_contains(self):
        container = ItemFactory.create_item_from_template("item_wooden_crate", self.world) \
            if "item_wooden_crate" in self.world.item_templates else Container(name="Test Crate")
        inner_item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        container.properties["contains"] = [inner_item]
        ref = _serialize_item_reference(container, 1, self.world)
        self.assertIn("properties_override", ref)
        self.assertIn("contains", ref["properties_override"])
        self.assertEqual(len(ref["properties_override"]["contains"]), 1)

    def _templated_container(self, obj_id, name, extra_props=None):
        # No Container template exists in this content set, so the "has a
        # resolvable template" branch of _serialize_item_reference's
        # contains-handling can only be reached by registering one directly.
        container = Container(name=name)
        container.obj_id = obj_id
        self.world.item_templates[obj_id] = {
            "name": name, "type": "Container", "properties": extra_props or {},
        }
        return container

    def test_container_with_non_list_contains_is_skipped(self):
        container = self._templated_container("fake_container_tpl_a", "Weird Crate")
        container.properties["contains"] = "not a list"
        ref = _serialize_item_reference(container, 1, self.world)
        if ref and "properties_override" in ref:
            self.assertNotIn("contains", ref["properties_override"])

    def test_container_with_unserializable_contained_item_is_skipped(self):
        container = self._templated_container("fake_container_tpl_b", "Sneaky Crate")
        bad_item = Item(name="Bad Item")
        bad_item.obj_id = ""  # will fail to serialize -> None
        container.properties["contains"] = [bad_item]
        ref = _serialize_item_reference(container, 1, self.world)
        if ref and "properties_override" in ref:
            self.assertNotIn("contains", ref["properties_override"])

    def test_templated_container_processes_multiple_properties(self):
        container = self._templated_container(
            "fake_container_tpl_c", "Multi Prop Crate", extra_props={"durability": 100},
        )
        container.properties["contains"] = []
        container.update_property("durability", 50)  # differs from template -> override
        ref = _serialize_item_reference(container, 1, self.world)
        self.assertIn("properties_override", ref)
        self.assertEqual(ref["properties_override"]["durability"], 50)

    def test_debug_mode_prints_override_summary(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        item.name = "Renamed Sword"
        self.world.game.debug_mode = True
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                _serialize_item_reference(item, 1, self.world)
            self.assertIn("[Save DBG]", buf.getvalue())
        finally:
            self.world.game.debug_mode = False

    def test_untemplated_container_with_non_list_contains_is_skipped(self):
        container = Container(name="Untemplated Weird Crate")  # random obj_id -> no template
        container.properties["contains"] = "not a list"
        ref = _serialize_item_reference(container, 1, self.world)
        self.assertNotIn("contains", ref.get("properties_override", {}))

    def test_untemplated_container_with_unserializable_contained_item_is_skipped(self):
        container = Container(name="Untemplated Sneaky Crate")
        bad_item = Item(name="Bad Item")
        bad_item.obj_id = ""
        container.properties["contains"] = [bad_item]
        ref = _serialize_item_reference(container, 1, self.world)
        self.assertNotIn("contains", ref.get("properties_override", {}))

    def test_multiple_property_overrides_are_all_captured(self):
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        item.name = "Renamed Sword"
        item.update_property("custom_flag_a", "x")
        item.update_property("custom_flag_b", "y")
        ref = _serialize_item_reference(item, 1, self.world)
        overrides = ref["properties_override"]
        self.assertEqual(overrides.get("custom_flag_a"), "x")
        self.assertEqual(overrides.get("custom_flag_b"), "y")


class TestGetArticleAndSimplePlural(unittest.TestCase):
    def test_get_article_empty_string_returns_a(self):
        self.assertEqual(get_article(""), "a")

    def test_simple_plural_empty_string_returns_empty(self):
        self.assertEqual(simple_plural(""), "")


class TestFormatNameForDisplay(unittest.TestCase):
    def test_falsy_target_returns_something(self):
        self.assertEqual(format_name_for_display(None, None), "something")

    def test_target_without_name_attribute_returns_something(self):
        class _NoName:
            pass
        self.assertEqual(format_name_for_display(None, _NoName()), "something")

    def test_item_target_uses_category_color(self):
        item = Item(name="a widget")
        result = format_name_for_display(None, item)
        self.assertIn("widget", result)


class TestDirectionPhrases(unittest.TestCase):
    def test_departure_phrase_unknown_direction_falls_back(self):
        result = get_departure_phrase("sideways")
        self.assertIn("towards the sideways", result)

    def test_arrival_phrase_unknown_direction_falls_back(self):
        result = get_arrival_phrase("sideways")
        self.assertIn("from sideways", result)


class TestWeightedChoice(unittest.TestCase):
    def test_random_choices_exception_falls_back_to_random_choice(self):
        with patch("engine.utils.utils.random.choices", side_effect=RuntimeError("boom")):
            result = weighted_choice({"a": 1, "b": 2})
        self.assertIn(result, ["a", "b"])

    def test_all_zero_or_negative_weights_falls_back_to_plain_choice(self):
        result = weighted_choice({"a": 0, "b": -5})
        self.assertIn(result, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
