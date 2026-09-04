# tests/singles/test_container_recursion.py
from typing import cast
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerRecursion(GameTestBase):

    def setUp(self):
        super().setUp()
        # Ensure template exists
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "value": 1, 
            "properties": { "is_open": True, "capacity": 100 }
        }

    def test_recursive_insertion_prevention(self):
        """Verify an item cannot be put into itself."""
        item_box = ItemFactory.create_item_from_template("box", self.world)
        
        if isinstance(item_box, Container) and self.player:
            box = cast(Container, item_box)
            self.player.inventory.add_item(box)
            
            # Attempt to put the box into itself
            # This should be blocked by logic in the 'put' command or container
            result = self.game.process_command(f"put {box.name} in {box.name}")
            
            self.assertIsNotNone(result)
            # The exact error message depends on the current implementation, 
            # but it should not succeed or crash.
            self.assertEqual(len(box.properties.get("contains", [])), 0, "Container should not contain itself.")

    def test_nested_recursive_insertion(self):
        """Verify A cannot go into B if B is inside A."""
        item_a = ItemFactory.create_item_from_template("box", self.world)
        item_b = ItemFactory.create_item_from_template("box", self.world)
        
        if isinstance(item_a, Container) and isinstance(item_b, Container) and self.player:
            box_a = cast(Container, item_a)
            box_b = cast(Container, item_b)
            box_a.name = "Box A"
            box_b.name = "Box B"
            
            self.player.inventory.add_item(box_a)
            self.player.inventory.add_item(box_b)
            
            # Put B in A
            self.game.process_command("put box b in box a")
            self.assertIn(box_b, box_a.properties.get("contains", []))
            
            # Attempt to put A in B (which is inside A)
            result = self.game.process_command("put box a in box b")
            
            self.assertEqual(len(box_b.properties.get("contains", [])), 0, "Should not allow circular nesting.")