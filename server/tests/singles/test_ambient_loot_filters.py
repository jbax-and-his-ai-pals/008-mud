"""Ambient loot uses content-defined NPC selectors, not setting-specific code."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory


class TestAmbientLootFilters(GameTestBase):
    def setUp(self):
        super().setUp()
        self.world.item_templates["item_filter_prize"] = {
            "type": "Item", "name": "filter prize", "stackable": True,
        }
        self._authored_loot = self.world.content_set.ruleset["loot"]
        self.world.content_set.ruleset["loot"] = {
            "ambient_pools": [{
                "chance": 1.0,
                "npc_tags_any": ["eligible"],
                "entries": [{"item_id": "item_filter_prize", "weight": 1}],
            }]
        }

    def _npc(self, template_id: str, tags: list[str]):
        self.world.npc_templates[template_id] = {
            "name": template_id, "faction": "hostile", "properties": {"loot_tags": tags},
        }
        npc = NPCFactory.create_npc_from_template(template_id, self.world)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.loot_table = {}
        return npc

    def test_matching_tag_receives_ambient_pool(self):
        npc = self._npc("eligible_npc", ["eligible"])
        with patch("engine.npcs.npc.random.random", return_value=0.0):
            dropped = npc.die(self.world)
        self.assertEqual(["item_filter_prize"], [item.obj_id for item in dropped])

    def test_nonmatching_tag_does_not_receive_ambient_pool(self):
        npc = self._npc("ineligible_npc", ["undead"])
        with patch("engine.npcs.npc.random.random", return_value=0.0):
            dropped = npc.die(self.world)
        self.assertEqual([], dropped)

    def _found_gem_ids(self):
        crafted_gem_ids = {
            recipe.result_item_id
            for recipe in self.game.crafting_manager.recipes.values()
            if self.world.item_templates.get(recipe.result_item_id, {}).get("type") == "Gem"
        }
        return {
            item_id for item_id, template in self.world.item_templates.items()
            if template.get("type") == "Gem" and item_id not in crafted_gem_ids
        }

    def test_fantasy_gem_catalogue_has_authored_ambient_sources(self):
        gem_ids = self._found_gem_ids()
        pools = self._authored_loot["ambient_pools"]
        ambient_item_ids = {
            entry["item_id"] for pool in pools for entry in pool["entries"]
        }
        self.assertTrue(gem_ids)
        self.assertTrue(gem_ids.issubset(ambient_item_ids))

    def test_fantasy_gem_catalogue_is_a_static_collection(self):
        gem_ids = self._found_gem_ids()
        collection = self.game.collection_manager.collections["riverside_gem_ledger"]
        self.assertEqual(gem_ids, set(collection["items"]))
