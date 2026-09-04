# tests/singles/test_container_encumbrance.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerEncumbrance(GameTestBase):

    def test_bag_of_holding_effect(self):
        """
        Verify if putting items in a container hides their weight from the player inventory.
        Current implementation: Containers have static weight in inventory.
        """
        # 1. Setup Container (Weight 1.0)
        self.world.item_templates["bag"] = {
            "type": "Container", "name": "Bag", "weight": 1.0, 
            "properties": { "capacity": 100, "is_open": True }
        }
        bag = ItemFactory.create_item_from_template("bag", self.world)
        
        # 2. Setup Heavy Item (Weight 50.0)
        self.world.item_templates["rock"] = { "type": "Item", "name": "Heavy Rock", "weight": 50.0 }
        rock = ItemFactory.create_item_from_template("rock", self.world)
        
        if bag and rock and self.player:
            # Add Bag to inventory
            self.player.inventory.add_item(bag)
            initial_weight = self.player.inventory.get_total_weight()
            self.assertEqual(initial_weight, 1.0)
            
            # Add Rock to inventory (Total 51.0)
            self.player.inventory.add_item(rock)
            self.assertEqual(self.player.inventory.get_total_weight(), 51.0)
            
            # 3. Move Rock into Bag
            self.game.process_command("put heavy rock in bag")
            
            # 4. Check Weight
            # If logic is standard MUD "container weight + contents", weight is still 51.0.
            # If logic is "Bag of Holding" (container static weight), weight drops to 1.0.
            # Based on `items/container.py` and `items/inventory/core.py`, the Inventory 
            # sums slot.item.weight. The Bag item has a static .weight attribute.
            # It does *not* dynamically update .weight based on contents.
            
            new_weight = self.player.inventory.get_total_weight()
            
            # Assertion for current implementation behavior (Bag of Holding effect)
            self.assertEqual(new_weight, 1.0, "Items inside container should not add to player encumbrance in current implementation.")