# tests/singles/test_resource_node_full.py
"""Coverage for engine/items/resource_node.py: the stackable/weight kwarg
overrides being stripped, gather() finding the required tool in equipment
(skipping the inventory scan), and a failed resource-item creation."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.resource_node import ResourceNode
from engine.items.weapon import Weapon


class TestResourceNodeInit(unittest.TestCase):
    def test_stackable_and_weight_kwargs_are_stripped(self):
        node = ResourceNode(name="Ore Vein", stackable=True, weight=1.0)
        self.assertFalse(node.stackable)
        self.assertEqual(node.weight, 9999)


class TestResourceNodeGather(GameTestBase):
    def setUp(self):
        super().setUp()
        self.node = ResourceNode(
            obj_id="test_gather_node", name="Ore Vein", description="A vein.",
            resource_item_id="item_iron_sword", tool_required="pickaxe", charges=3,
        )

    def test_tool_found_in_equipment_skips_inventory_scan(self):
        pickaxe = Weapon(name="Equipped Pickaxe", damage=1)
        pickaxe.update_property("tool_type", "pickaxe")
        self.player.inventory.add_item(pickaxe)
        self.player.equip_item(pickaxe, slot_name="main_hand")
        result = self.node.gather(self.player, self.world)
        self.assertIn("gather", result.lower())

    def test_failed_resource_creation_reports_nothing_useful(self):
        pickaxe = Weapon(name="Pickaxe", damage=1)
        pickaxe.update_property("tool_type", "pickaxe")
        self.player.inventory.add_item(pickaxe)
        with patch("engine.items.item_factory.ItemFactory.create_item_from_template", return_value=None):
            result = self.node.gather(self.player, self.world)
        self.assertIn("nothing useful", result)


if __name__ == "__main__":
    unittest.main()
