# tests/singles/test_resource_node_full.py
"""Coverage for engine/items/resource_node.py: the stackable/weight kwarg
overrides being stripped, gather() finding the required tool in equipment
(skipping the inventory scan), a failed resource-item creation, accurate
recovery-time reporting, cross-world alternate-source/substitute
discovery, and partial-harvest trickle recovery."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.resource_node import ResourceNode
from engine.items.weapon import Weapon
from engine.world.region import Region
from engine.world.room import Room


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


class TestResourceNodeRecoveryDaysLeft(GameTestBase):
    def setUp(self):
        super().setUp()
        self.node = ResourceNode(
            obj_id="test_recovery_node", name="Test Vein", description="A vein.",
            resource_item_id="item_iron_sword", tool_required="pickaxe",
            charges=5, respawn_days=3,
        )

    def test_none_when_the_node_still_has_charges(self):
        self.assertIsNone(self.node.recovery_days_left(self.world))

    def test_none_when_the_node_is_not_renewable(self):
        self.node.update_property("charges", 0)
        self.node.update_property("respawn_days", 0)
        self.node.update_property("depleted_day", 0)
        self.assertIsNone(self.node.recovery_days_left(self.world))

    def test_counts_down_accurately_as_days_pass(self):
        self.node.update_property("charges", 0)
        self.node.update_property("depleted_day", 0)
        self.assertEqual(3, self.node.recovery_days_left(self.world))
        self.game.time_manager.game_time = 2 * 86400.0
        self.assertEqual(1, self.node.recovery_days_left(self.world))

    def test_none_once_fully_recovered(self):
        self.node.update_property("charges", 0)
        self.node.update_property("depleted_day", 0)
        self.game.time_manager.game_time = 3 * 86400.0
        self.assertIsNone(self.node.recovery_days_left(self.world))
        self.assertEqual(5, self.node.available_charges(self.world))


class TestResourceNodeAlternatesAndSubstitutes(GameTestBase):
    """Uses the real fantasy_frontier content set (loaded by GameTestBase)
    rather than synthetic nodes, since the alternate-source pair (the two
    fishing spots) and the substitute pair (herb bed / berry bramble) are
    both real, already-authored content."""

    def _node_in(self, region_id, room_id):
        room = self.world.get_region(region_id).get_room(room_id)
        return next(item for item in room.items if isinstance(item, ResourceNode))

    def test_fishing_spots_are_alternate_sources_for_each_other(self):
        river_spot = self._node_in("town", "fishing_hut")
        sea_spot = self._node_in("portbridge", "fishing_pier")
        self.assertIn("sheltered fishing spot (Fishing Pier)", river_spot.find_alternate_sources(self.world))
        self.assertIn("calm fishing hole (Fishing Hut)", sea_spot.find_alternate_sources(self.world))

    def test_herb_bed_and_berry_bramble_are_authored_substitutes(self):
        herb_bed = self._node_in("town", "community_garden")
        berry_bramble = self._node_in("forest", "forest_edge")
        self.assertIn("berry bramble (Forest Edge)", herb_bed.find_substitutes(self.world))
        self.assertIn("herb bed (Community Garden)", berry_bramble.find_substitutes(self.world))

    def test_node_with_no_authored_relationships_has_no_matches(self):
        fallen_bough = self._node_in("farmland", "orchard_west")
        self.assertEqual([], fallen_bough.find_alternate_sources(self.world))
        self.assertEqual([], fallen_bough.find_substitutes(self.world))

    def test_private_house_and_quest_instance_regions_are_excluded(self):
        river_spot = self._node_in("town", "fishing_hut")

        house_region = Region(name="Player House", description="A private home.", obj_id="dynamic_player_house_test123")
        house_room = Room(name="Interior", description="A house interior.", obj_id="house_interior_test")
        house_pond = ResourceNode(
            obj_id="house_pond_test", name="house pond", description="A pond.",
            resource_item_id="item_fresh_fish", tool_required="fishing_net", charges=3,
        )
        house_room.add_item(house_pond)
        house_region.add_room("house_interior_test", house_room)
        self.world.add_region("dynamic_player_house_test123", house_region)

        instance_region = Region(name="Quest Instance", description="A quest instance.", obj_id="instance_test_quest")
        instance_room = Room(name="Hidden Grove", description="A grove.", obj_id="instance_room_test")
        instance_spot = ResourceNode(
            obj_id="instance_spot_test", name="hidden spring", description="A spring.",
            resource_item_id="item_fresh_fish", tool_required="fishing_net", charges=3,
        )
        instance_room.add_item(instance_spot)
        instance_region.add_room("instance_room_test", instance_room)
        self.world.add_region("instance_test_quest", instance_region)

        alternates = river_spot.find_alternate_sources(self.world)
        self.assertIn("sheltered fishing spot (Fishing Pier)", alternates)
        self.assertNotIn("house pond (Interior)", alternates)
        self.assertNotIn("hidden spring (Hidden Grove)", alternates)


class TestResourceNodePartialHarvestRecovery(GameTestBase):
    """A partial harvest used to leave a node frozen forever -- charges
    only ever recovered once a gather drove them all the way to zero.
    These confirm the new trickle recovery: a partially-harvested node
    heals back over time too, without changing the existing, already-
    tuned full-depletion timing at all."""

    def setUp(self):
        super().setUp()
        self.node = ResourceNode(
            obj_id="test_partial_node", name="Test Patch", description="A patch.",
            resource_item_id="item_iron_sword", tool_required="pickaxe",
            charges=3, respawn_days=2,
        )
        pickaxe = Weapon(name="Pickaxe", damage=1)
        pickaxe.update_property("tool_type", "pickaxe")
        self.player.inventory.add_item(pickaxe)

    def test_partial_harvest_does_not_recover_before_the_interval_elapses(self):
        self.node.gather(self.player, self.world)  # 3 -> 2, still partial
        self.assertEqual(2, self.node.available_charges(self.world))
        self.game.time_manager.game_time = 1 * 86400.0  # interval is 2 days
        self.assertEqual(2, self.node.available_charges(self.world))

    def test_partial_harvest_trickles_back_after_the_interval(self):
        self.node.gather(self.player, self.world)  # 3 -> 2
        self.game.time_manager.game_time = 2 * 86400.0
        self.assertEqual(3, self.node.available_charges(self.world))

    def test_partial_harvest_recovery_caps_at_max_charges(self):
        self.node.gather(self.player, self.world)  # 3 -> 2
        self.game.time_manager.game_time = 10 * 86400.0
        self.assertEqual(3, self.node.available_charges(self.world))

    def test_full_depletion_keeps_the_original_all_at_once_recovery(self):
        self.node.gather(self.player, self.world)  # 3 -> 2
        self.node.gather(self.player, self.world)  # 2 -> 1
        self.node.gather(self.player, self.world)  # 1 -> 0, fully depleted
        self.assertEqual(0, self.node.available_charges(self.world))
        self.game.time_manager.game_time = 1 * 86400.0
        self.assertEqual(0, self.node.available_charges(self.world))
        self.game.time_manager.game_time = 2 * 86400.0
        self.assertEqual(3, self.node.available_charges(self.world))


if __name__ == "__main__":
    unittest.main()
