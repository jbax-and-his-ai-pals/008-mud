# tests/singles/test_collection_manager_full.py
"""Coverage for engine/core/collection_manager.py: __init__'s data_root
mismatch guard, _load_collections' exception handling, discovery's
already-tracked-progress skip, turn_in's non-collector guard, item-scan
skips (no collection_id, duplicate-in-loop), a failed removal being
skipped, _check_completion's already-completed short-circuit,
_grant_rewards' xp/multi-item branches, and get_collection_status' unknown-
collection guard and in-inventory-but-not-turned-in branch."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.core.collection_manager import CollectionManager
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory


class TestInit(GameTestBase):
    def test_mismatched_data_root_raises(self):
        with self.assertRaises(ValueError):
            CollectionManager(self.world, data_root="/some/other/path")


class TestLoadCollectionsErrorHandling(GameTestBase):
    def test_malformed_collections_file_is_caught_and_reset(self):
        tmp_root = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp_root, "collections.json"), "w") as f:
                f.write("{not valid json")
            original_data_root = self.world.data_root
            self.world.data_root = tmp_root
            try:
                manager = CollectionManager(self.world, data_root=tmp_root)
            finally:
                self.world.data_root = original_data_root
            self.assertEqual(manager.collections, {})
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)


class _CollectionTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = self.game.collection_manager
        self.manager.collections["bugs"] = {
            "name": "Rare Bugs", "items": ["beetle", "butterfly"], "rewards": {},
        }
        self.world.item_templates["beetle"] = {
            "type": "Junk", "name": "Golden Beetle", "value": 1,
            "properties": {"collection_id": "bugs"},
        }
        self.world.item_templates["butterfly"] = {
            "type": "Junk", "name": "Blue Butterfly", "value": 1,
            "properties": {"collection_id": "bugs"},
        }

    def _collector(self, instance_id="collector_npc"):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id=instance_id)
        self.world.add_npc(npc)
        npc.properties["is_collector"] = True
        return npc


class TestDiscovery(_CollectionTestBase):
    def test_already_tracked_collection_does_not_reset_progress(self):
        beetle = ItemFactory.create_item_from_template("beetle", self.world)
        self.player.collections_progress["bugs"] = ["already_turned_in_id"]
        self.manager.handle_collection_discovery(self.player, beetle)
        self.assertEqual(self.player.collections_progress["bugs"], ["already_turned_in_id"])


class TestTurnInItems(_CollectionTestBase):
    def test_non_collector_npc_is_not_interested(self):
        villager = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="not_a_collector")
        self.world.add_npc(villager)
        result = self.manager.turn_in_items(self.player, villager)
        self.assertIn("not interested", result)

    def test_item_without_collection_id_is_skipped(self):
        collector = self._collector()
        junk = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(junk)
        result = self.manager.turn_in_items(self.player, collector)
        self.assertIn("don't have any new artifacts", result)

    def test_duplicate_stacked_item_is_only_queued_once(self):
        collector = self._collector()
        beetle_a = ItemFactory.create_item_from_template("beetle", self.world)
        beetle_b = ItemFactory.create_item_from_template("beetle", self.world)
        beetle_b.obj_id = beetle_a.obj_id  # simulate a duplicate stack entry
        self.player.inventory.add_item(beetle_a)
        self.player.inventory.slots.append(type(self.player.inventory.slots[0])(beetle_b, 1))
        result = self.manager.turn_in_items(self.player, collector)
        self.assertEqual(result.count("Donated"), 1)

    def test_failed_removal_is_skipped(self):
        # The scan phase pre-initializes collections_progress["bugs"] = []
        # regardless of removal outcome; what a failed removal actually
        # skips is appending the item's obj_id to that list.
        collector = self._collector()
        beetle = ItemFactory.create_item_from_template("beetle", self.world)
        self.player.inventory.add_item(beetle)
        with patch.object(self.player.inventory, "remove_item", return_value=(None, 0, "mock failure")):
            result = self.manager.turn_in_items(self.player, collector)
        self.assertNotIn(beetle.obj_id, self.player.collections_progress.get("bugs", []))


class TestCheckCompletion(_CollectionTestBase):
    def test_already_completed_collection_is_a_noop(self):
        self.player.collections_completed["bugs"] = True
        self.player.collections_progress["bugs"] = ["beetle", "butterfly"]
        messages = []
        self.manager._check_completion(self.player, "bugs", messages)
        self.assertEqual(messages, [])


class TestGrantRewards(_CollectionTestBase):
    def test_xp_reward_grants_experience(self):
        col_def = {"rewards": {"xp": 50}}
        original_xp = self.player.runtime_state.progression.experience
        msg = self.manager._grant_rewards(self.player, col_def)
        self.assertIn("Gained 50 XP", msg)
        self.assertGreater(self.player.runtime_state.progression.experience, original_xp)

    def test_item_reward_factory_failure_is_skipped(self):
        col_def = {"rewards": {"items": [
            {"item_id": "totally_bogus_item_template_xyz", "quantity": 1},
            {"item_id": "item_iron_sword", "quantity": 1},
        ]}}
        msg = self.manager._grant_rewards(self.player, col_def)
        self.assertIn("Received", msg)
        self.assertEqual(msg.count("Received"), 1)

    def test_multiple_item_rewards_are_all_granted(self):
        col_def = {"rewards": {"items": [
            {"item_id": "item_iron_sword", "quantity": 1},
            {"item_id": "item_healing_potion_small", "quantity": 2},
        ]}}
        msg = self.manager._grant_rewards(self.player, col_def)
        self.assertIn("Received", msg)
        self.assertIsNotNone(self.player.inventory.find_item_by_name("Iron Sword") or self.player.inventory.find_item_by_name("sword"))
        self.assertGreaterEqual(self.player.inventory.count_item("item_healing_potion_small"), 2)


class TestGetCollectionStatus(_CollectionTestBase):
    def test_unknown_collection_returns_generic_message(self):
        result = self.manager.get_collection_status(self.player, "totally_bogus_collection_xyz")
        self.assertEqual(result, "Unknown collection.")

    def test_item_in_inventory_but_not_turned_in_shows_in_inventory_marker(self):
        beetle = ItemFactory.create_item_from_template("beetle", self.world)
        self.player.inventory.add_item(beetle)
        result = self.manager.get_collection_status(self.player, "bugs")
        self.assertIn("(In Inventory)", result)
        self.assertIn("[+]", result)


if __name__ == "__main__":
    unittest.main()
