# tests/singles/test_container_authoring.py
"""An authored container's inventory: what a template's `contains` actually does.

`night_shift` is the first content set to author a container's contents in the
template rather than generating them at runtime, and authoring three of them found
two ways the engine was ignoring what content wrote:

* **`properties.contains` never reached the constructor.** `ItemFactory` pops a
  template's `properties` out before instantiating the class, and `Container.__init__`
  is what turns those `{item_id, quantity}` references into items -- it reads them
  from its own kwargs. So every authored container came out empty. The factory's
  property loop then skipped `contains` on the explicit assumption the constructor
  had already hydrated it, which is why nothing ever complained: two comments
  describing an intent, and neither of them implemented.
* **`quantity` was read and discarded.** A `{item_id, quantity: 2}` entry put one
  instance in. A container holds instances and has no stack model at all, so the
  honest reading of a count is that many instances.

Both are pinned here rather than only through `night_shift`, because the next set
to author a till or a chest should fail a small, named test rather than a journey.
"""

import unittest
from pathlib import Path

from engine.items.container import Container
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestAuthoredContents(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        self.addCleanup(self.server.shutdown)
        self.world = self.server.world

    def _container(self, **properties):
        template = {
            "type": "Container", "name": "probe crate", "weight": 5, "value": 1,
            "stackable": False, "properties": dict(properties),
        }
        self.world.item_templates["item_probe_crate"] = template
        return ItemFactory.create_item_from_template("item_probe_crate", self.world)

    def test_contents_authored_on_the_template_exist_on_the_instance(self):
        crate = self._container(contains=[{"item_id": "item_iron_sword", "quantity": 2}])
        self.assertIsInstance(crate, Container)
        self.assertEqual(
            ["item_iron_sword", "item_iron_sword"],
            [item.obj_id for item in crate.properties.get("contains", [])],
        )

    def test_a_quantity_of_two_is_two_items(self):
        crate = self._container(contains=[
            {"item_id": "item_iron_sword", "quantity": 1},
            {"item_id": "item_gold_coin", "quantity": 3},
        ])
        ids = [item.obj_id for item in crate.properties.get("contains", [])]
        self.assertEqual(1, ids.count("item_iron_sword"))
        self.assertEqual(3, ids.count("item_gold_coin"))

    def test_an_unusable_quantity_is_one_item(self):
        for bad in (0, -2, True, "two", None):
            with self.subTest(quantity=bad):
                crate = self._container(contains=[{"item_id": "item_iron_sword", "quantity": bad}])
                self.assertEqual(1, len(crate.properties.get("contains", [])))

    def test_container_state_travels_with_the_template(self):
        crate = self._container(
            locked=True, lock_difficulty=25, capacity=12,
            is_open=False, contains=[{"item_id": "item_iron_sword"}],
        )
        self.assertTrue(crate.properties["locked"])
        self.assertEqual(25, crate.properties["lock_difficulty"])
        self.assertEqual(12, crate.properties["capacity"])
        self.assertFalse(crate.properties["is_open"])

    def test_listed_contents_group_only_what_stacks(self):
        """Two instances of a non-stackable thing are two entries in the listing.

        The container has no stack model, so `quantity` made instances; the
        listing groups *stackable* ones and leaves the rest as they are. An author
        writing "two swords" gets two lines, and writing "three coins" gets one.
        """
        crate = self._container(contains=[
            {"item_id": "item_iron_sword", "quantity": 2},
            {"item_id": "item_gold_coin", "quantity": 3},
        ])
        crate.properties["is_open"] = True
        listed = crate.list_contents()
        self.assertIn("iron sword", listed)
        self.assertIn("gold coin (x3)", listed)
        self.assertEqual(2, listed.count("iron sword"))

    def test_an_ordinary_item_is_unaffected_by_the_container_keys(self):
        template = {
            "type": "Weapon", "name": "probe blade", "weight": 1.0, "value": 5,
            "stackable": False, "equip_slot": ["main_hand"],
            "properties": {"defense": 1},
        }
        self.world.item_templates["item_probe_blade"] = template
        blade = ItemFactory.create_item_from_template("item_probe_blade", self.world)
        self.assertIsNotNone(blade)
        self.assertEqual(1, blade.get_property("defense"))
        self.assertFalse(hasattr(blade, "contains"))


class TestTheShippedContainers(unittest.TestCase):
    """What the sets actually author, read through the same path."""

    def test_the_depot_containers_hold_what_they_say(self):
        import json

        depot = REPO_ROOT / "content_sets" / "night_shift"
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(depot),
            deterministic_test_mode=True,
        )
        self.addCleanup(server.shutdown)
        items = json.loads((depot / "data" / "items" / "depot_items.json").read_text(encoding="utf-8"))
        expected = {
            item_id: len([entry for entry in payload["properties"]["contains"]
                          for _ in range(int(entry.get("quantity", 1)))])
            for item_id, payload in items.items()
            if isinstance(payload.get("properties"), dict) and payload["properties"].get("contains")
        }
        self.assertTrue(expected, "the set authors at least one container")

        placed = {}
        for region in server.world.regions.values():
            for room in region.rooms.values():
                for item in room.items:
                    if isinstance(item, Container):
                        placed[item.obj_id] = len(item.properties.get("contains", []))
        for item_id, count in expected.items():
            with self.subTest(container=item_id):
                self.assertIn(item_id, placed, "the container is placed in a room")
                self.assertEqual(count, placed[item_id])


if __name__ == "__main__":
    unittest.main()
