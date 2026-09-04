# tests/singles/test_collection_status.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestCollectionStatus(GameTestBase):

    def setUp(self):
        super().setUp()
        self.manager = self.game.collection_manager
        
        # Register a mock collection
        self.manager.collections["bugs"] = {
            "name": "Rare Bugs",
            "items": ["beetle", "butterfly"],
            "rewards": { "gold": 10 }
        }
        
        # Mock Items
        self.world.item_templates["beetle"] = {"type": "Junk", "name": "Golden Beetle", "value": 1, "properties": {"collection_id": "bugs"}}
        self.world.item_templates["butterfly"] = {"type": "Junk", "name": "Blue Butterfly", "value": 1, "properties": {"collection_id": "bugs"}}

    def test_status_display_logic(self):
        """Verify status text correctly marks found vs missing items."""
        # 1. Turn in one item
        self.player.collections_progress["bugs"] = ["beetle"]
        
        # 2. Get Status
        status = self.manager.get_collection_status(self.player, "bugs")
        
        # 3. Assert Visuals
        self.assertIn("[x]", status) # Beetle checked
        self.assertIn("Golden Beetle", status)
        self.assertIn("[ ]", status) # Butterfly unchecked
        self.assertIn("Blue Butterfly", status)
        self.assertIn("In Progress", status)

    def test_duplicate_turn_in_prevention(self):
        """Verify the same item type cannot be turned in twice for credit."""
        collector = NPCFactory.create_npc_from_template("curator", self.world)
        if not collector: return
        collector.properties["is_collector"] = True
        
        # 1. Give Beetle
        beetle = ItemFactory.create_item_from_template("beetle", self.world)
        if beetle:
            self.player.inventory.add_item(beetle)
            self.manager.turn_in_items(self.player, collector)
            
        # Verify Progress
        self.assertEqual(len(self.player.collections_progress["bugs"]), 1)
        
        # 2. Give Another Beetle
        beetle2 = ItemFactory.create_item_from_template("beetle", self.world)
        if beetle2:
            self.player.inventory.add_item(beetle2)
            result = self.manager.turn_in_items(self.player, collector)
            
        # Verify Progress (Should still be 1)
        self.assertEqual(len(self.player.collections_progress["bugs"]), 1)
        # Beetle 2 should still be in inventory (or consumed? Logic in manager says it filters `items_to_remove` based on existing progress)
        # `turn_in_items` logic checks `if item.obj_id not in player.collections_progress`.
        # So it shouldn't take it.
        self.assertEqual(self.player.inventory.count_item("beetle"), 1)