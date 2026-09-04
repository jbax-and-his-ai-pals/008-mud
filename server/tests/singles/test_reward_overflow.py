# tests/singles/test_reward_overflow.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestRewardOverflow(GameTestBase):

    def test_collection_reward_full_inv(self):
        """Verify rewards handle full inventory gracefully (current behavior check)."""
        # 1. Setup Collection
        self.game.collection_manager.collections["overflow_test"] = {
            "name": "Overflow", "items": ["token"],
            "rewards": { "items": [{"item_id": "reward_gem", "quantity": 1}] }
        }
        
        # Templates
        self.world.item_templates["token"] = {"type": "Junk", "name": "Token", "value": 1, "properties": {"collection_id": "overflow_test"}}
        self.world.item_templates["reward_gem"] = {"type": "Gem", "name": "Reward Gem", "value": 100}
        
        # 2. Fill Inventory
        self.player.inventory.max_slots = 1
        self.player.inventory.slots = self.player.inventory.slots[:1] # Resize
        
        token = ItemFactory.create_item_from_template("token", self.world)
        if token: self.player.inventory.add_item(token)
        
        self.assertEqual(self.player.inventory.get_empty_slots(), 0)
        
        # 3. Setup Collector
        collector = NPCFactory.create_npc_from_template("curator", self.world)
        if collector:
            collector.properties["is_collector"] = True
            
            # 4. Turn In
            # Token is removed -> Slot opens -> Reward added?
            # Or does reward logic happen before removal?
            # Logic in `turn_in_items`: remove_item -> update progress -> check completion -> grant rewards.
            # So slot SHOULD free up.
            
            msg = self.game.collection_manager.turn_in_items(self.player, collector)
            
            # 5. Assert
            self.assertIn("COLLECTION COMPLETE", msg)
            self.assertEqual(self.player.inventory.count_item("token"), 0)
            self.assertEqual(self.player.inventory.count_item("reward_gem"), 1, "Reward should fit in the slot freed by the turned-in item.")