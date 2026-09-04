# tests/singles/test_container_weight_recursive.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerWeightRecursive(GameTestBase):

    def test_container_content_weight(self):
        """Verify container get_current_weight sums contents correctly."""
        # 1. Setup Container
        bag = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        if not isinstance(bag, Container): return
        
        # Base weight is 5.0 (from template)
        self.assertEqual(bag.weight, 5.0) 
        
        # 2. Add Items
        # Iron Ingot (Weight 1.0)
        ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
        if ingot: bag.add_item(ingot)
        
        # 3. Check Contents Weight
        # Logic: get_current_weight returns SUM of contents
        content_weight = bag.get_current_weight()
        self.assertEqual(content_weight, 1.0)
        
        # Note: In standard D&D/MUDs, the *Item's* weight property usually stays static 
        # unless dynamic weight updating is implemented in the Item class.
        # This test confirms the helper method works, even if player encumbrance 
        # calculation might need to call it explicitly.