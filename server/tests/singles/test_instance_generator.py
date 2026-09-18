"""The instance pipeline is content-neutral, proved with a non-fantasy family.

The point of the contract work is that a content set which has never heard of
gems gets the same generated instances. A test that only rolls rubies cannot
show that: every key it checks (`gem_size`) could still be produced by a branch
on the word. So these tests build a small content set out of nothing but
declarations -- a salvaged component family, its own bands, its own property
prefix, its own name shape -- and assert the engine treats it exactly like the
shipped stones.

If any of these fail, the resolver has grown a genre assumption.
"""

import unittest

from engine.contracts.registry import SCHEMA_VERSION, ContractRegistry
from engine.items.instance_generator import InstanceGenerator


class _World:
    """Minimal world: item templates and whatever registry a test hands it."""

    def __init__(self, templates=None, registry=None):
        self.item_templates = templates or {}
        self.contract_registry = registry


def _component_world(prefix="component", name_template=None, capabilities=("generated_instance",)):
    profile = {
        "id": "salvage_grade",
        "item_family": "salvaged_component",
        "property_prefix": prefix,
        "rarity_tiers": [
            {"id": "scrap", "rank": 1, "weight": 90},
            {"id": "serviceable", "rank": 3, "weight": 10},
        ],
        "size_tiers": [
            {"id": "micro", "label": "micro", "score": 1, "value_multiplier": 0.5, "weight_multiplier": 0.5},
            {"id": "bulk", "label": "bulk", "score": 3, "value_multiplier": 2.0, "weight_multiplier": 2.0},
        ],
        "quality_tiers": [
            {"id": "worn", "label": "worn", "score": 1, "value_multiplier": 0.4},
            {"id": "true", "label": "true", "score": 3, "value_multiplier": 1.0},
        ],
    }
    if name_template:
        profile["name_template"] = name_template
    registry = ContractRegistry()
    registry.ingest({
        "schema_version": SCHEMA_VERSION,
        "item_families": [{
            "id": "salvaged_component",
            "label": "Salvaged components",
            "item_class": "Junk",
            "capabilities": list(capabilities),
            "generation_profile": "salvage_grade",
        }],
        "generation_profiles": [profile],
    })
    assert registry.issues == [], registry.issues
    return _World(
        templates={
            "item_servo_cluster": {
                "type": "Item",
                "name": "servo cluster",
                "value": 40,
                "weight": 0.6,
                "stackable": True,
                "item_family": "salvaged_component",
            },
        },
        registry=registry,
    )


class TestInstanceGeneratorIsGenreNeutral(unittest.TestCase):
    def test_a_declared_family_rolls_instances_without_any_gem_vocabulary(self):
        world = _component_world()
        self.assertTrue(InstanceGenerator.is_generated_template(world, "item_servo_cluster"))
        self.assertEqual("item_servo_cluster", InstanceGenerator.pick_template_id(world, level=1))

        item = InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster")
        self.assertIsNotNone(item)
        self.assertIn(item.get_property("component_size"), ("micro", "bulk"))
        self.assertIn(item.get_property("component_quality"), ("worn", "true"))
        self.assertIn(item.get_property("component_rarity"), ("scrap", "serviceable"))
        self.assertEqual("item_servo_cluster", item.get_property("component_type_id"))
        # The neutral vocabulary is written for every family.
        self.assertEqual(item.get_property("component_size"), item.get_property("instance_size"))
        # And nothing invented a gem key for a set that never mentions one.
        self.assertIsNone(item.get_property("gem_size"))
        self.assertIsNone(item.get_property("gem_rarity"))

    def test_the_rolled_bands_drive_name_value_and_weight(self):
        world = _component_world()
        item = InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster")
        self.assertIsNotNone(item)
        size = item.get_property("instance_size")
        quality = item.get_property("instance_quality")
        expected_value = {
            ("micro", "worn"): 8, ("micro", "true"): 20,
            ("bulk", "worn"): 32, ("bulk", "true"): 80,
        }[(size, quality)]
        self.assertEqual(expected_value, item.value)
        self.assertAlmostEqual(0.6 * (0.5 if size == "micro" else 2.0), item.weight)
        self.assertFalse(item.stackable, "distinct instances must not stack")
        self.assertIn(item.get_property("instance_quality_label"), item.name)

    def test_a_profile_shapes_the_name_it_wants(self):
        world = _component_world(name_template="{base} ({quality}, {size})")
        item = InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster")
        self.assertIsNotNone(item)
        self.assertEqual(
            "servo cluster (%s, %s)" % (
                item.get_property("instance_quality_label"),
                item.get_property("instance_size_label"),
            ),
            item.name,
        )

    def test_an_unused_band_leaves_no_gap_or_empty_group(self):
        world = _component_world(name_template="{quality} {size} {base} ({rarity})")
        # A quality tier whose label is empty is content choosing to say nothing
        # about quality; the name must still read cleanly.
        for _ in range(20):
            item = InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster")
            self.assertNotIn("  ", item.name)
            self.assertNotIn("()", item.name)
            self.assertNotIn(" )", item.name)
            self.assertEqual(item.name, item.name.strip())

    def test_the_capability_is_what_makes_a_family_roll(self):
        """A family that does not declare `generated_instance` is not rolled."""
        world = _component_world(capabilities=("vendor_trash",))
        self.assertFalse(InstanceGenerator.is_generated_template(world, "item_servo_cluster"))
        self.assertIsNone(InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster"))

    def test_an_undeclared_field_in_a_name_template_falls_back_rather_than_crashing(self):
        world = _component_world(name_template="{quality} {colour} {base}")
        item = InstanceGenerator.generate(world, level=5, template_id="item_servo_cluster")
        self.assertIsNotNone(item)
        self.assertNotIn("{colour}", item.name)
        self.assertIn("servo cluster", item.name)
