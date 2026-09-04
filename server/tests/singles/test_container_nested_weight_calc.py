# tests/singles/test_container_nested_weight_calc.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerNestedWeightCalc(GameTestBase):

    def test_nested_container_masks_weight(self):
        """Verify that putting a heavy item in a container masks its weight from the player (Bag of Holding mechanic)."""
        # 1. Setup Heavy Item (100 lbs)
        self.world.item_templates["anvil"] = {"type": "Item", "name": "Anvil", "weight": 100.0}
        anvil = ItemFactory.create_item_from_template("anvil", self.world)
        
        # 2. Setup Container (Weight 1 lbs)
        self.world.item_templates["magic_bag"] = {
            "type": "Container", "name": "Bag", "weight": 1.0, 
            "properties": {"capacity": 200.0, "is_open": True}
        }
        bag = ItemFactory.create_item_from_template("magic_bag", self.world)
        
        self.assertIsNotNone(anvil)
        self.assertIsNotNone(bag)
        
        if anvil and isinstance(bag, Container):
            # 3. Add Bag to Player
            self.player.inventory.add_item(bag)
            self.assertEqual(self.player.inventory.get_total_weight(), 1.0)
            
            # 4. Put Anvil in Bag (bypass player carry limit for the test setup)
            # We add anvil to bag directly
            bag.add_item(anvil)
            
            # 5. Assert Player Weight
            # The player carries the Bag (1.0). The Bag carries the Anvil.
            self.assertEqual(self.player.inventory.get_total_weight(), 1.0, 
                             "Standard MUD container often acts as a Bag of Holding regarding parent encumbrance.")