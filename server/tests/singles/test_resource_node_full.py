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

    def test_missing_tool_message_confirms_neither_slot_has_one(self):
        result = self.node.gather(self.player, self.world)
        self.assertIn("You need a pickaxe", result)
        self.assertIn("don't seem to be carrying or wearing one", result)


class TestResourceNodeDepletedMessage(GameTestBase):
    def test_renewable_node_reports_days_until_recovery(self):
        node = ResourceNode(
            obj_id="test_depleted_renewable", name="Herb Patch",
            resource_item_id="item_iron_sword", tool_required="pickaxe",
            charges=0, respawn_days=3,
        )
        node.update_property("depleted_day", 0)
        result = node.gather(self.player, self.world)
        self.assertIn("has been depleted", result)
        self.assertIn("recover in about 3 day", result)

    def test_non_renewable_node_keeps_the_plain_message(self):
        node = ResourceNode(
            obj_id="test_depleted_finite", name="Ore Deposit",
            resource_item_id="item_iron_sword", tool_required="pickaxe",
            charges=0, respawn_days=0,
        )
        result = node.gather(self.player, self.world)
        self.assertEqual("The Ore Deposit has been depleted.", result)


if __name__ == "__main__":
    unittest.main()
