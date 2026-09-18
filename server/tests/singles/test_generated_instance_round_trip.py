"""A rolled instance keeps its resolved identity through save and load.

The completion gate for the contract work is blunt: *a generated item
round-trips through inventory/save/load with its resolved identity intact*. It
is worth a test of its own because the failure is silent and asymmetric. The
template id is the only thing a save is required to contain, so a loader can
always rebuild *an* item of the right species -- and quietly hand back the
authored one. The player then owns a "Perfect magnificent ruby" that is worth a
plain ruby's value, and nothing anywhere reports a problem.

What "resolved identity" means here, and why each part is checked:

* the rolled bands (rarity, size, quality) -- the reason the instance exists;
* the name assembled from those bands;
* the value and weight derived from them, which is what the economy and the
  inventory ceiling actually read;
* the cross-system `material_quality*` trio, which crafting and quest
  objectives read without knowing anything about instances.
"""

from tests.fixtures import GameTestBase
from engine.items.instance_generator import InstanceGenerator
from engine.items.inventory import Inventory


class TestGeneratedInstanceRoundTrip(GameTestBase):
    def _rolled_ruby(self):
        """A ruby whose rolled identity differs from its authored template."""
        template = self.world.item_templates["item_rose_quartz"]
        item = InstanceGenerator.generate(
            self.world, level=8, template_id="item_rose_quartz", quality_score=5,
        )
        self.assertIsNotNone(item)
        # Without this the test could pass by round-tripping a plain template.
        self.assertNotEqual(template["value"], item.value)
        self.assertNotEqual(template["name"], item.name)
        self.assertEqual(5, item.get_property("material_quality_score"))
        return item

    def _round_trip(self, item):
        inventory = Inventory(max_slots=5, max_weight=100.0)
        added, message = inventory.add_item(item)
        self.assertTrue(added, message)
        payload = inventory.to_dict(self.world)
        reloaded = Inventory.from_dict(payload, self.world)
        restored = reloaded.slots[0].item
        self.assertIsNotNone(restored)
        return restored

    def test_the_rolled_name_survives(self):
        item = self._rolled_ruby()
        self.assertEqual(item.name, self._round_trip(item).name)

    def test_the_rolled_value_and_weight_survive(self):
        """Value is derived from the bands, so losing it loses the roll.

        It is also the field a crafted quality tier multiplies, which is why
        this covers more than gems: any item whose value is not the template's
        was silently reverting on load.
        """
        item = self._rolled_ruby()
        restored = self._round_trip(item)
        self.assertEqual(item.value, restored.value)
        self.assertEqual(item.weight, restored.weight)

    def test_the_rolled_bands_and_their_cross_system_score_survive(self):
        item = self._rolled_ruby()
        restored = self._round_trip(item)
        for key in (
            "instance_rarity",
            "instance_size",
            "instance_size_score",
            "instance_quality",
            "instance_quality_score",
            "material_quality",
            "material_quality_label",
            "material_quality_score",
        ):
            self.assertEqual(item.get_property(key), restored.get_property(key), key)
        self.assertFalse(restored.stackable)

    def test_a_real_save_file_reloads_the_instance_not_the_template(self):
        """The whole path, not just the inventory half of it."""
        item = self._rolled_ruby()
        added, message = self.player.inventory.add_item(item)
        self.assertTrue(added, message)

        self.assertTrue(self.world.save_manager.save("instance_round_trip.json", player=self.player))
        ok, _time_state, _weather_state = self.world.save_manager.load("instance_round_trip.json")
        self.assertTrue(ok, "the save did not load")

        loaded = [slot.item for slot in self.world.player.inventory.slots if slot.item]
        matches = [candidate for candidate in loaded if candidate.obj_id == "item_rose_quartz"]
        self.assertEqual(1, len(matches), f"expected the ruby back, got {[c.name for c in loaded]}")
        reloaded = matches[0]
        self.assertEqual(item.name, reloaded.name)
        self.assertEqual(item.value, reloaded.value)
        self.assertEqual(item.weight, reloaded.weight)
        self.assertFalse(reloaded.stackable)
        self.assertEqual(
            item.get_property("material_quality_score"),
            reloaded.get_property("material_quality_score"),
        )
