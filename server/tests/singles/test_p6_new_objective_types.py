# tests/singles/test_p6_new_objective_types.py
"""Coverage for the five new quest objective types added to finish P6:
relationship, discover_n, craft_quality, gather_types, deliver_multi.

Each reuses existing tracked state (relationship score, the advancement
ledger, recipe quality tiers, resource item ids, NPC give-to-target) rather
than inventing new player state -- these tests drive the real event each
type hooks into (a tick-driven check, a craft, a gather, a give) and assert
the resulting quest-state transition, mirroring how test_quest_manager_
lifecycle.py already exercises clear_region/kill directly."""

from tests.fixtures import GameTestBase
from engine.commands.interaction.use_give import give_handler
from engine.items.item_factory import ItemFactory
from engine.items.resource_node import ResourceNode
from engine.items.weapon import Weapon


def _base_quest(objective, **overrides):
    quest = {
        "instance_id": "test_quest",
        "title": "Test Quest",
        "state": "active",
        "giver_instance_id": None,
        "current_stage_index": 0,
        "completion_check_enabled": True,
        "stages": [{"objective": objective, "turn_in_id": None}],
        "rewards": {},
    }
    quest.update(overrides)
    return quest


class TestRelationshipObjective(GameTestBase):
    def setUp(self):
        super().setUp()
        self.objective = {
            "type": "relationship", "target_npc_template_id": "blacksmith",
            "required_score": 30, "npc_name": "Grenda",
        }
        self.quest = _base_quest(self.objective)
        self.player.runtime_state.quests.active["test_quest"] = self.quest

    def test_stays_active_below_the_required_score(self):
        self.player.npc_relationships["blacksmith"] = 10
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("active", self.quest["state"])

    def test_completes_once_the_required_score_is_reached(self):
        self.player.npc_relationships["blacksmith"] = 30
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("ready_to_complete", self.quest["state"])

    def test_a_different_npcs_relationship_does_not_count(self):
        self.player.npc_relationships["merchant"] = 100
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("active", self.quest["state"])


class TestDiscoverNObjective(GameTestBase):
    def setUp(self):
        super().setUp()
        self.objective = {"type": "discover_n", "kind": "discovery", "required_count": 2}
        self.quest = _base_quest(self.objective)
        self.player.runtime_state.quests.active["test_quest"] = self.quest
        self.player.advancement_entries = set()

    def test_stays_active_below_the_required_count(self):
        self.player.advancement_entries = {"discovery:item_pearl"}
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("active", self.quest["state"])

    def test_completes_once_the_required_count_is_reached(self):
        self.player.advancement_entries = {"discovery:item_pearl", "discovery:item_coral_gem"}
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("ready_to_complete", self.quest["state"])

    def test_entries_of_a_different_kind_do_not_count(self):
        self.player.advancement_entries = {"region:town", "region:forest", "landmark:foo"}
        self.world.quest_manager.check_quest_completion(self.player)
        self.assertEqual("active", self.quest["state"])


class TestCraftQualityObjective(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.crafting_manager
        self.objective = {
            "type": "craft_quality", "recipe_id": "tie_wildflower_posy", "required_quality_id": "masterwork",
        }
        self.quest = _base_quest(self.objective)
        self.player.runtime_state.quests.active["test_quest"] = self.quest
        herbs = ItemFactory.create_item_from_template("item_wild_herbs", self.world)
        self.player.inventory.add_item(herbs, 2)

    def test_a_craft_below_the_required_tier_leaves_the_quest_active(self):
        self.manager.craft(self.player, "tie_wildflower_posy")  # first craft -> "simple", not masterwork
        self.assertEqual("active", self.quest["state"])

    def test_a_craft_reaching_the_required_tier_completes_the_quest(self):
        self.player.recipe_craft_counts["tie_wildflower_posy"] = 7  # next craft (8th) reaches masterwork
        self.manager.craft(self.player, "tie_wildflower_posy")
        self.assertEqual("ready_to_complete", self.quest["state"])

    def test_crafting_a_different_recipe_does_not_count(self):
        softwood = ItemFactory.create_item_from_template("item_softwood", self.world)
        self.player.inventory.add_item(softwood, 2)
        self.player.recipe_craft_counts["carve_riverside_charm"] = 7
        self.manager.craft(self.player, "carve_riverside_charm")
        self.assertEqual("active", self.quest["state"])


class TestGatherTypesObjective(GameTestBase):
    def setUp(self):
        super().setUp()
        self.objective = {
            "type": "gather_types",
            "required_item_ids": ["item_wild_herbs", "item_softwood"],
        }
        self.quest = _base_quest(self.objective)
        self.player.runtime_state.quests.active["test_quest"] = self.quest
        knife = Weapon(name="Knife", damage=1)
        knife.update_property("tool_type", "foraging_knife")
        axe = Weapon(name="Axe", damage=1)
        axe.update_property("tool_type", "hand_axe")
        self.player.inventory.add_item(knife)
        self.player.inventory.add_item(axe)
        self.herb_node = ResourceNode(
            obj_id="test_herb_node", name="herb patch", description="x",
            resource_item_id="item_wild_herbs", tool_required="foraging_knife", charges=3,
        )
        self.wood_node = ResourceNode(
            obj_id="test_wood_node", name="fallen branch", description="x",
            resource_item_id="item_softwood", tool_required="hand_axe", charges=3,
        )

    def test_gathering_one_required_type_leaves_the_quest_active_with_progress(self):
        self.herb_node.gather(self.player, self.world)
        self.assertEqual("active", self.quest["state"])
        self.assertEqual(["item_wild_herbs"], self.objective["gathered_item_ids"])

    def test_gathering_all_required_types_completes_the_quest(self):
        self.herb_node.gather(self.player, self.world)
        self.wood_node.gather(self.player, self.world)
        self.assertEqual("ready_to_complete", self.quest["state"])

    def test_gathering_an_unrelated_resource_does_not_count(self):
        clay_node = ResourceNode(
            obj_id="test_clay_node", name="clay bank", description="x",
            resource_item_id="item_river_clay", tool_required="foraging_knife", charges=3,
        )
        clay_node.gather(self.player, self.world)
        self.assertEqual([], self.objective.get("gathered_item_ids", []))

    def test_gathering_the_same_type_twice_only_counts_once(self):
        self.herb_node.gather(self.player, self.world)
        self.herb_node.update_property("charges", 3)
        self.herb_node.gather(self.player, self.world)
        self.assertEqual(["item_wild_herbs"], self.objective["gathered_item_ids"])


class TestDeliverMultiObjective(GameTestBase):
    def setUp(self):
        super().setUp()
        self.objective = {
            "type": "deliver_multi", "item_template_id": "item_river_clay",
            "recipients": [
                {"template_id": "blacksmith", "name": "Grenda"},
                {"template_id": "merchant", "name": "Talia"},
            ],
        }
        self.quest = _base_quest(self.objective, title="Two Deliveries")
        self.player.runtime_state.quests.active["test_quest"] = self.quest
        clay = ItemFactory.create_item_from_template("item_river_clay", self.world)
        self.player.inventory.add_item(clay, 2)
        self.grenda = next(n for n in self.world.npcs.values() if n.template_id == "blacksmith")
        self.talia = next(n for n in self.world.npcs.values() if n.template_id == "merchant")

    def _give_clay_to(self, npc):
        self.player.current_region_id = npc.current_region_id
        self.player.current_room_id = npc.current_room_id
        return give_handler(["river", "clay", "to", npc.name], {"world": self.world, "player": self.player})

    def test_first_delivery_reports_progress_without_completing(self):
        result = self._give_clay_to(self.grenda)
        self.assertIn("1/2 delivered", result)
        self.assertIn("Talia", result)
        self.assertEqual("active", self.quest["state"])
        self.assertEqual(1, self.player.inventory.count_item("item_river_clay"))

    def test_second_delivery_completes_the_quest(self):
        self._give_clay_to(self.grenda)
        result = self._give_clay_to(self.talia)
        self.assertIn("Quest Complete", result)
        self.assertNotIn("test_quest", self.player.runtime_state.quests.active)
        self.assertIn("test_quest", self.player.runtime_state.quests.completed)

    def test_delivering_to_the_same_recipient_twice_is_rejected(self):
        self._give_clay_to(self.grenda)
        result = self._give_clay_to(self.grenda)
        self.assertIn("already given", result)
        # The second attempt must not have consumed a second item.
        self.assertEqual(1, self.player.inventory.count_item("item_river_clay"))


if __name__ == "__main__":
    import unittest
    unittest.main()
