# tests/singles/test_container_exact_capacity.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerExactCapacity(GameTestBase):

    def test_exact_fit(self):
        """Verify items fitting exactly into capacity are accepted."""
        # Container Cap 10.0
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "weight": 1,
            "properties": {"capacity": 10.0, "is_open": True}
        }
        box = ItemFactory.create_item_from_template("box", self.world)
        
        # Item Weight 10.0
        self.world.item_templates["brick"] = {"type": "Item", "name": "Brick", "weight": 10.0}
        brick = ItemFactory.create_item_from_template("brick", self.world)
        
        if isinstance(box, Container) and brick:
            self.player.inventory.add_item(box)
            self.player.inventory.add_item(brick)
            
            # Act: Put Brick in Box
            result = self.game.process_command("put Brick in Box")
            
            self.assertIsNotNone(result)
            if result:
                self.assertIn("You put", result)
            self.assertEqual(box.get_current_weight(), 10.0)

    def test_slight_overflow(self):
        """Verify items exceeding capacity are rejected."""
        # Container Cap 10.0
        box = ItemFactory.create_item_from_template("box", self.world) # From template above
        
        # Item Weight 10.1
        self.world.item_templates["heavy_brick"] = {"type": "Item", "name": "Heavy", "weight": 10.1}
        heavy = ItemFactory.create_item_from_template("heavy_brick", self.world)
        
        if isinstance(box, Container) and heavy:
            self.player.inventory.add_item(box)
            self.player.inventory.add_item(heavy)
            
            result = self.game.process_command("put Heavy in Box")
            
            self.assertIsNotNone(result)
            if result:
                self.assertIn("too full", result)
            self.assertEqual(box.get_current_weight(), 0.0)