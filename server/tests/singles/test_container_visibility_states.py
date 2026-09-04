# tests/singles/test_container_visibility_states.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestContainerVisibilityStates(GameTestBase):

    def test_look_in_closed_vs_open(self):
        """Verify 'look in' only works on open containers."""
        # 1. Setup
        bag = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        content = ItemFactory.create_item_from_template("item_apple", self.world) # Assume apple exists or generic
        
        if isinstance(bag, Container) and content:
            bag.name = "Box"
            bag.properties["is_open"] = False
            bag.add_item(content)
            self.player.inventory.add_item(bag)
            
            # 2. Look In (Closed)
            result_closed = self.game.process_command("look in Box")
            self.assertIsNotNone(result_closed)
            if result_closed:
                self.assertIn("closed", result_closed.lower())
                self.assertNotIn(content.name, result_closed)
            
            # 3. Open
            self.game.process_command("open Box")
            
            # 4. Look In (Open)
            result_open = self.game.process_command("look in Box")
            self.assertIsNotNone(result_open)
            if result_open:
                self.assertIn(content.name, result_open)