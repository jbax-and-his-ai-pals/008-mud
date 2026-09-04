# tests/singles/test_collections.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from typing import Dict, Any

class TestCollections(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.manager = self.game.collection_manager
        
        # Register a mock collection manually
        self.manager.collections["test_set"] = {
            "name": "Test Set",
            "description": "A set of test items.",
            "items": ["item_test_bead"],
            "rewards": { "gold": 100 }
        }
        
        # Register a mock item template directly into the world
        self.world.item_templates["item_test_bead"] = {
            "type": "Junk", "name": "test bead", "value": 1, 
            "properties": { "collection_id": "test_set" }
        }

    def test_turn_in_and_completion(self):
        """Verify collection turn-in logic and rewards."""
        # 1. Create a Collector NPC
        # We try 'curator' first, but fallback to creating a custom one to ensure test stability
        collector = NPCFactory.create_npc_from_template("curator", self.world)
        if not collector:
            # Fallback creation logic if template missing
            collector = NPCFactory.create_npc_from_template("wandering_villager", self.world)
            
        self.assertIsNotNone(collector, "Failed to create collector NPC.")
        
        if collector:
            # Force the property necessary for the test
            collector.properties["is_collector"] = True
            self.world.add_npc(collector)
            
            # 2. Give Player the Item
            bead = ItemFactory.create_item_from_template("item_test_bead", self.world)
            self.assertIsNotNone(bead, "Failed to create test item.")
            
            if bead:
                self.player.inventory.add_item(bead)
                
                # 3. Turn In
                result = self.manager.turn_in_items(self.player, collector)
                
                # 4. Assertions
                self.assertIn("Donated test bead", result)
                self.assertIn("COLLECTION COMPLETE", result)
                
                # Check Item Removed
                self.assertEqual(self.player.inventory.count_item("item_test_bead"), 0)
                
                # Check Progress Tracking
                self.assertIn("test_set", self.player.collections_completed)
                self.assertTrue(self.player.collections_completed["test_set"])
                
                # Check Reward (Start gold is 0 usually)
                self.assertEqual(self.player.runtime_state.gold, 100)
