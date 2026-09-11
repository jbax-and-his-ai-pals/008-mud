# tests/singles/test_fishing_content.py
"""Coverage for the fishing content pass: the two new fishing-spot
ResourceNode templates, their real placement in town and Portbridge, the
fishing net wired as their required tool, and the rare-catch yield-table
entries that finally give item_pearl/item_coral_gem (both already listed
in the gem ledger collection, previously with no drop source anywhere)
a real home. The generic gather/ResourceNode mechanics themselves are
already covered by test_gathering_command.py and test_resource_node_full.py --
this file is about the content, not the engine."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory


class TestFishingSpotPlacement(GameTestBase):
    def test_river_spot_is_in_the_fishing_hut(self):
        hut = self.world.get_region("town").get_room("fishing_hut")
        self.assertTrue(any(i.obj_id == "node_river_fishing_spot" for i in hut.items))

    def test_sea_spot_is_at_the_fishing_pier(self):
        pier = self.world.get_region("portbridge").get_room("fishing_pier")
        self.assertTrue(any(i.obj_id == "node_sea_fishing_spot" for i in pier.items))

    def test_net_is_wired_as_the_required_tool_for_both_spots(self):
        for template_id in ("node_river_fishing_spot", "node_sea_fishing_spot"):
            template = self.world.item_templates[template_id]
            self.assertEqual("fishing_net", template["properties"]["tool_required"])
        self.assertEqual("fishing_net", self.world.item_templates["item_fishing_net"]["properties"]["tool_type"])


class TestGatheringWithoutANet(GameTestBase):
    def test_river_spot_reports_missing_net(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "fishing_hut"
        result = self.game.process_command("gather calm fishing hole")
        self.assertIn("fishing_net", result)

    def test_sea_spot_reports_missing_net(self):
        self.player.current_region_id = "portbridge"
        self.player.current_room_id = "fishing_pier"
        result = self.game.process_command("gather sheltered fishing spot")
        self.assertIn("fishing_net", result)


class TestGatheringWithANet(GameTestBase):
    def setUp(self):
        super().setUp()
        net = ItemFactory.create_item_from_template("item_fishing_net", self.world)
        self.player.inventory.add_item(net)

    def test_ordinary_catch_is_fresh_fish(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "fishing_hut"
        with patch("engine.items.resource_node.random.random", return_value=0.99):
            result = self.game.process_command("gather calm fishing hole")
        self.assertIn("fresh fish", result)
        self.assertEqual(1, self.player.inventory.count_item("item_fresh_fish"))

    def test_rare_river_catch_is_a_quality_stamped_pearl(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "fishing_hut"
        with patch("engine.items.resource_node.random.random", return_value=0.0):
            result = self.game.process_command("gather calm fishing hole")
        self.assertIn("pearl", result.lower())
        pearl_slot = next(s for s in self.player.inventory.slots if s.item and s.item.obj_id == "item_pearl")
        self.assertEqual(2, pearl_slot.item.get_property("material_quality_score"))
        self.assertEqual("Lustrous", pearl_slot.item.get_property("material_quality_label"))
        # The gem ledger collection should notice this discovery immediately.
        self.assertIn("riverside_gem_ledger", self.player.collections_progress)

    def test_rare_sea_catch_is_a_quality_stamped_coral(self):
        self.player.current_region_id = "portbridge"
        self.player.current_room_id = "fishing_pier"
        with patch("engine.items.resource_node.random.random", return_value=0.0):
            result = self.game.process_command("gather sheltered fishing spot")
        self.assertIn("coral", result.lower())
        coral_slot = next(s for s in self.player.inventory.slots if s.item and s.item.obj_id == "item_coral_gem")
        self.assertEqual(2, coral_slot.item.get_property("material_quality_score"))
        self.assertEqual("Vivid", coral_slot.item.get_property("material_quality_label"))
        self.assertIn("riverside_gem_ledger", self.player.collections_progress)

    def test_charges_deplete_and_spot_eventually_runs_dry(self):
        self.player.current_region_id = "town"
        self.player.current_room_id = "fishing_hut"
        with patch("engine.items.resource_node.random.random", return_value=0.99):
            for _ in range(4):
                result = self.game.process_command("gather calm fishing hole")
                self.assertIn("fresh fish", result)
            depleted = self.game.process_command("gather calm fishing hole")
        self.assertIn("depleted", depleted)


class TestFishingDiscoverabilityHint(GameTestBase):
    def test_asking_fenn_about_fishing_points_to_the_pier(self):
        self.player.current_region_id = "portbridge"
        self.player.current_room_id = "fish_market"
        result = self.game.process_command("ask Fenn about fishing")
        self.assertIn("fishing pier", result.lower())
