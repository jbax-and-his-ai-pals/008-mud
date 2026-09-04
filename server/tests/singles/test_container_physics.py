# tests/singles/test_container_physics.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerPhysics(GameTestBase):
    
    def setUp(self):
        super().setUp()
        # Inject templates to ensure they exist for the test
        self.world.item_templates["item_empty_crate"] = {
            "type": "Container", "name": "Crate", "value": 1, "weight": 5.0,
            "properties": { "capacity": 10.0, "is_open": True } # Setup capacity here
        }
        self.world.item_templates["item_anvil"] = {
            "type": "Item", "name": "Anvil", "value": 100, "weight": 200.0
        }
        self.world.item_templates["item_ruby"] = {
            "type": "Gem", "name": "Ruby", "value": 100, "weight": 0.1
        }

    def test_container_capacity_limit(self):
        """Verify items cannot be put into a container if weight limit exceeded."""
        # 1. Create a Bag with small capacity
        bag = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        
        self.assertIsNotNone(bag, "Failed to create bag item")
        if not isinstance(bag, Container):
            self.fail("Bag is not a Container instance")
            return
        
        bag.name = "Small Bag"
        # properties set in template, but ensuring here
        bag.properties["capacity"] = 10.0
        bag.properties["is_open"] = True
        
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        if rid and room_id:
            self.world.add_item_to_room(rid, room_id, bag)
            
        # 2. Create Heavy Item (Anvil: 200.0)
        anvil = ItemFactory.create_item_from_template("item_anvil", self.world)
        self.assertIsNotNone(anvil)
        if not anvil: return
        
        # Force add to inventory to bypass player weight check
        # We want to test the CONTAINER'S limit, not the player's inability to pick it up
        self.player.inventory.slots[0].add(anvil)
        
        # 3. Attempt to Put Anvil (Weight 200 > Cap 10)
        result = self.game.process_command("put anvil in bag")
        
        # 4. Assert Failure
        self.assertIsNotNone(result, "Command processed but returned None")
        if result:
            self.assertIn("too full", result)
        self.assertEqual(len(bag.properties["contains"]), 0)
        
        # 5. Verify smaller item fits
        gem = ItemFactory.create_item_from_template("item_ruby", self.world) # Weight 0.1
        if gem:
            # FIX: Force add gem to inventory slot 1. 
            # Normal add_item() would fail because player is carrying the 200lb anvil.
            self.player.inventory.slots[1].add(gem)
            
            result_success = self.game.process_command("put ruby in bag")
            
            self.assertIsNotNone(result_success, "Command processed but returned None")
            if result_success:
                self.assertIn("You put", result_success)
            self.assertEqual(len(bag.properties["contains"]), 1)