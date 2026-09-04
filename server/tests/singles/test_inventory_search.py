# tests/singles/test_inventory_search.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestInventorySearch(GameTestBase):

    def test_exact_vs_partial_matching(self):
        """Verify inventory correctly distinguishes between specific items."""
        # 1. Setup overlapping names
        self.world.item_templates["p1"] = {"type": "Item", "name": "potion", "value": 1}
        self.world.item_templates["p2"] = {"type": "Item", "name": "super potion", "value": 5}
        
        item1 = ItemFactory.create_item_from_template("p1", self.world)
        item2 = ItemFactory.create_item_from_template("p2", self.world)
        
        if item1 and item2 and self.player:
            self.player.inventory.add_item(item1)
            self.player.inventory.add_item(item2)
            
            # 2. Test Exact Match (via find_item_by_name with partial=False)
            found = self.player.inventory.find_item_by_name("potion", partial=False)
            self.assertEqual(found, item1, "Exact match should ignore 'super potion'.")
            
            # 3. Test Partial Match
            found_partial = self.player.inventory.find_item_by_name("super")
            self.assertEqual(found_partial, item2)

    def test_search_by_obj_id(self):
        """Verify items can be found by their template/object ID."""
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if item and self.player:
            self.player.inventory.add_item(item)
            
            found = self.player.inventory.find_item_by_name("item_iron_sword")
            self.assertEqual(found, item)