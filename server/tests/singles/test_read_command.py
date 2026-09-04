# tests/singles/test_read_command.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestReadCommand(GameTestBase):
    def test_read_book(self):
        """Verify read alias works like look/examine."""
        # Create item
        self.world.item_templates["book"] = {
            "type": "Item", "name": "Old Book", 
            "description": "It says 'Hello World'."
        }
        book = ItemFactory.create_item_from_template("book", self.world)
        if book:
            self.player.inventory.add_item(book)
            
            res = self.game.process_command("read old book")
            
            self.assertIsNotNone(res)
            if res:
                self.assertIn("Hello World", res)