# tests/singles/test_item_factory_full.py
"""Coverage for engine/items/item_factory.py: create_random_loot's delegation,
create_item's kwarg-filtering/extra-properties/exception paths, from_dict's
template-first-then-class-fallback logic (including the Container branch and
exception handling), get_template, and create_item_from_template's procedural
(random-spell-scroll) generation, scroll-template fallback, and the various
override/property-merging edge cases.

Note: create_item_from_template's `if 'is_procedural' in new_template['properties']:`
False branch is left untested as unreachable -- `template_props` (used to
gate entry into this whole block on `is_procedural` being truthy) is the
literal `properties` dict from the template, and `new_template` is a
`copy.deepcopy(template)` taken before anything mutates it, so
`new_template['properties']` is guaranteed to still contain the same
'is_procedural' key by the time this check runs."""

from unittest.mock import patch, MagicMock

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.item import Item
from engine.items.weapon import Weapon
from engine.items.container import Container


class TestCreateRandomLoot(GameTestBase):
    def test_delegates_to_loot_generator(self):
        fake_item = Item(obj_id="loot1", name="Loot", description="x")
        with patch("engine.items.loot_generator.LootGenerator.generate_loot", return_value=fake_item) as mock_gen:
            result = ItemFactory.create_random_loot("some_base", self.world, level=5)
        mock_gen.assert_called_once_with("some_base", self.world, 5)
        self.assertIs(fake_item, result)


class TestCreateItem(GameTestBase):
    def test_unknown_type_falls_back_to_base_item(self):
        item = ItemFactory.create_item("NotARealType", obj_id="ci1", name="Thing", description="x")
        self.assertIsNotNone(item)
        self.assertEqual("Item", item.__class__.__name__)

    def test_totally_missing_item_class_map_entry_returns_none(self):
        with patch.dict("engine.items.item_factory.ITEM_CLASS_MAP", {}, clear=True):
            result = ItemFactory.create_item("Item", obj_id="ci_none", name="X", description="x")
        self.assertIsNone(result)

    def test_valid_type_constructs_correct_class(self):
        item = ItemFactory.create_item("Weapon", obj_id="ci2", name="Sword", description="x")
        self.assertIsInstance(item, Weapon)

    def test_unrecognized_kwarg_becomes_extra_property_when_no_var_kwargs(self):
        # Every built-in item class accepts **kwargs (and Item.__init__
        # itself applies unrecognized kwargs as properties), so this
        # specific extra_properties/update_property code path in
        # create_item is only reachable with a class that genuinely
        # defines no **kwargs of its own.
        class _NoKwargsItem(Item):
            def __init__(self, obj_id=None, name="X", description="d"):
                super().__init__(obj_id=obj_id, name=name, description=description)

        with patch.dict("engine.items.item_factory.ITEM_CLASS_MAP", {"NoKwargs": _NoKwargsItem}):
            item = ItemFactory.create_item(
                "NoKwargs", obj_id="ci3", name="Thing", description="x",
                custom_flag="yes", another_flag="also",
                # Not a valid_param for _NoKwargsItem, has_kwargs is False,
                # but 'weight' is in the hard-coded exclusion list -- it is
                # silently dropped rather than becoming an extra property.
                weight=99.0,
            )
        self.assertEqual("yes", item.get_property("custom_flag"))
        self.assertEqual("also", item.get_property("another_flag"))
        self.assertEqual(1.0, item.weight)  # the excluded 'weight' kwarg was silently dropped

    def test_kwarg_routed_through_var_kwargs_when_class_accepts_them(self):
        # Container.__init__ accepts **kwargs, so a key that ISN'T one of
        # its own named parameters (unlike 'locked') should be passed
        # straight through as a constructor kwarg instead of being routed
        # through create_item's own extra_properties fallback.
        item = ItemFactory.create_item(
            "Container", obj_id="ci4", name="Box", description="x", custom_container_flag=True,
        )
        self.assertIsInstance(item, Container)
        self.assertTrue(item.properties["custom_container_flag"])

    def test_construction_exception_returns_none(self):
        with patch("engine.items.item_factory.inspect.signature", side_effect=RuntimeError("boom")):
            result = ItemFactory.create_item("Item", obj_id="ci5", name="X", description="x")
        self.assertIsNone(result)


class TestFromDict(GameTestBase):
    def test_uses_template_when_id_and_world_present(self):
        data = {"obj_id": "item_starter_dagger", "properties_override": {"name": "Custom Dagger"}}
        item = ItemFactory.from_dict(data, self.world)
        self.assertEqual("Custom Dagger", item.name)

    def test_falls_back_to_class_from_dict_when_template_lookup_fails(self):
        data = {"obj_id": "not_a_real_template_id", "name": "Fallback Item", "type": "Item"}
        item = ItemFactory.from_dict(data, self.world)
        self.assertIsNotNone(item)
        self.assertEqual("Fallback Item", item.name)

    def test_no_world_skips_template_lookup_and_uses_class_from_dict(self):
        data = {"obj_id": "item_starter_dagger", "name": "No World Item", "type": "Item"}
        item = ItemFactory.from_dict(data, None)
        self.assertIsNotNone(item)
        self.assertEqual("No World Item", item.name)

    def test_unknown_type_falls_back_to_item_class(self):
        data = {"name": "Weird Type Item", "type": "TotallyMadeUpType"}
        item = ItemFactory.from_dict(data, None)
        self.assertIsNotNone(item)
        self.assertEqual("Item", item.__class__.__name__)

    def test_missing_item_class_entirely_returns_none(self):
        with patch.dict("engine.items.item_factory.ITEM_CLASS_MAP", {}, clear=True):
            result = ItemFactory.from_dict({"name": "X", "type": "Item"}, None)
        self.assertIsNone(result)

    def test_container_type_dispatches_to_container_from_dict(self):
        data = {"name": "A Box", "type": "Container", "properties": {"locked": True}}
        item = ItemFactory.from_dict(data, self.world)
        self.assertIsInstance(item, Container)
        self.assertTrue(item.properties["locked"])

    def test_exception_during_from_dict_returns_none(self):
        data = {"name": "X", "type": "Item"}
        with patch("engine.items.item.Item.from_dict", side_effect=RuntimeError("boom")):
            result = ItemFactory.from_dict(data, None)
        self.assertIsNone(result)


class TestGetTemplate(GameTestBase):
    def test_returns_template_when_present(self):
        template = ItemFactory.get_template("item_starter_dagger", self.world)
        self.assertIsNotNone(template)

    def test_returns_none_without_world(self):
        self.assertIsNone(ItemFactory.get_template("item_starter_dagger", None))

    def test_returns_none_when_world_lacks_item_templates(self):
        class _BareWorld:
            pass
        self.assertIsNone(ItemFactory.get_template("item_starter_dagger", _BareWorld()))


class TestCreateItemFromTemplateBasics(GameTestBase):
    def test_no_world_returns_none(self):
        self.assertIsNone(ItemFactory.create_item_from_template("item_starter_dagger", None))

    def test_world_without_item_templates_returns_none(self):
        class _BareWorld:
            pass
        self.assertIsNone(ItemFactory.create_item_from_template("item_starter_dagger", _BareWorld()))

    def test_unknown_item_id_returns_none(self):
        self.assertIsNone(ItemFactory.create_item_from_template("not_a_real_template_at_all", self.world))

    def test_scroll_prefixed_unknown_id_falls_back_to_scroll_random_template(self):
        self.world.item_templates["item_scroll_random"] = {
            "name": "Random Scroll", "type": "Item", "value": 10,
        }
        item = ItemFactory.create_item_from_template("item_scroll_totally_unknown", self.world)
        self.assertIsNotNone(item)

    def test_scroll_prefixed_id_without_fallback_template_returns_none(self):
        self.world.item_templates.pop("item_scroll_random", None)
        self.assertIsNone(ItemFactory.create_item_from_template("item_scroll_still_unknown", self.world))

    def test_unknown_item_class_in_template_returns_none(self):
        self.world.item_templates["weird_type_template"] = {"name": "Weird", "type": "NotARealItemType"}
        self.assertIsNone(ItemFactory.create_item_from_template("weird_type_template", self.world))

    def test_construction_exception_returns_none(self):
        self.world.item_templates["exploding_template"] = {"name": "Boom", "type": "Item"}
        with patch("engine.items.item_factory.inspect.signature", side_effect=RuntimeError("boom")):
            result = ItemFactory.create_item_from_template("exploding_template", self.world)
        self.assertIsNone(result)


class TestCreateItemFromTemplateOverrides(GameTestBase):
    def test_properties_override_kwarg_merges_into_overrides(self):
        item = ItemFactory.create_item_from_template(
            "item_starter_dagger", self.world, properties_override={"name": "Renamed Dagger"},
        )
        self.assertEqual("Renamed Dagger", item.name)

    def test_equip_slot_from_overrides_is_applied(self):
        item = ItemFactory.create_item_from_template(
            "item_starter_dagger", self.world, equip_slot=["main_hand"],
        )
        self.assertEqual(["main_hand"], item.get_property("equip_slot"))

    def test_equip_slot_from_template_properties_is_applied_when_not_overridden(self):
        self.world.item_templates["slot_from_template"] = {
            "name": "Slotted", "type": "Weapon",
            "properties": {"equip_slot": ["off_hand"]},
        }
        item = ItemFactory.create_item_from_template("slot_from_template", self.world)
        self.assertEqual(["off_hand"], item.get_property("equip_slot"))

    def test_extra_override_not_in_valid_params_lands_in_properties(self):
        self.world.item_templates["strict_template"] = {"name": "Strict", "type": "Item"}
        item = ItemFactory.create_item_from_template(
            "strict_template", self.world, totally_custom_flag="present",
        )
        self.assertEqual("present", item.properties.get("totally_custom_flag"))

    def test_var_kwargs_class_receives_full_creation_args(self):
        self.world.item_templates["box_template"] = {
            "name": "Boxy", "type": "Container", "properties": {"capacity": 5.0},
        }
        item = ItemFactory.create_item_from_template("box_template", self.world, locked=True)
        self.assertIsInstance(item, Container)
        self.assertTrue(item.properties["locked"])

    def test_extra_override_lands_in_properties_for_a_class_with_no_var_kwargs(self):
        # As in TestCreateItem, every built-in item class accepts **kwargs,
        # so create_item_from_template's own `if not has_kwargs:` branch
        # for filtering init_args and re-applying leftover overrides is
        # only reachable with a class that genuinely has none.
        class _NoKwargsItem(Item):
            def __init__(self, obj_id=None, name="X", description="d"):
                super().__init__(obj_id=obj_id, name=name, description=description)

        self.world.item_templates["no_kwargs_template"] = {"name": "Plain", "type": "NoKwargs"}
        with patch.dict("engine.items.item_factory.ITEM_CLASS_MAP", {"NoKwargs": _NoKwargsItem}):
            item = ItemFactory.create_item_from_template(
                "no_kwargs_template", self.world,
                totally_custom_flag="present", another_custom_flag="also_present",
                # 'name' IS a valid param for _NoKwargsItem, so this leftover
                # override must be skipped rather than re-applied as a property.
                name="Renamed Plain",
            )
        self.assertIsInstance(item, _NoKwargsItem)
        self.assertEqual("Renamed Plain", item.name)
        self.assertEqual("present", item.properties.get("totally_custom_flag"))
        self.assertEqual("also_present", item.properties.get("another_custom_flag"))
        self.assertNotIn("name", item.properties)


class TestCreateItemFromTemplateProcedural(GameTestBase):
    def _spell_scroll_template(self):
        self.world.item_templates["procedural_scroll"] = {
            "name": "Mystery Scroll", "type": "Item", "value": 5,
            "properties": {
                "is_procedural": True,
                "procedural_type": "random_spell_scroll",
            },
        }

    def test_random_spell_scroll_generates_named_scroll(self):
        self._spell_scroll_template()
        item = ItemFactory.create_item_from_template("procedural_scroll", self.world)
        self.assertIsNotNone(item)
        self.assertIn("Scroll of", item.name)
        self.assertIsNotNone(item.properties.get("spell_to_learn"))
        self.assertNotIn("is_procedural", item.properties)
        self.assertNotIn("procedural_type", item.properties)

    def test_random_spell_scroll_with_no_eligible_spells_keeps_template_name(self):
        self._spell_scroll_template()
        with patch("engine.items.item_factory.SPELL_REGISTRY", {}):
            item = ItemFactory.create_item_from_template("procedural_scroll", self.world)
        self.assertIsNotNone(item)
        self.assertEqual("Mystery Scroll", item.name)

    def test_explicit_spell_to_learn_override_skips_random_selection(self):
        self._spell_scroll_template()
        item = ItemFactory.create_item_from_template(
            "procedural_scroll", self.world, spell_to_learn="magic_missile",
        )
        self.assertIsNotNone(item)
        self.assertEqual("magic_missile", item.properties.get("spell_to_learn"))
        # Name should remain the un-randomized template name since the
        # spell-selection branch was skipped entirely.
        self.assertEqual("Mystery Scroll", item.name)

    def test_procedural_without_procedural_type_key_is_handled_gracefully(self):
        self.world.item_templates["no_proc_type"] = {
            "name": "Vague Procedural", "type": "Item",
            "properties": {"is_procedural": True},  # no "procedural_type" key at all
        }
        item = ItemFactory.create_item_from_template("no_proc_type", self.world)
        self.assertIsNotNone(item)
        self.assertNotIn("is_procedural", item.properties)
        self.assertNotIn("procedural_type", item.properties)

    def test_procedural_non_spell_scroll_type_skips_generation_logic(self):
        self.world.item_templates["other_procedural"] = {
            "name": "Odd Procedural", "type": "Item",
            "properties": {"is_procedural": True, "procedural_type": "something_else"},
        }
        item = ItemFactory.create_item_from_template("other_procedural", self.world)
        self.assertIsNotNone(item)
        self.assertEqual("Odd Procedural", item.name)
        self.assertNotIn("is_procedural", item.properties)


if __name__ == "__main__":
    import unittest
    unittest.main()
