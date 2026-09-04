# tests/singles/test_consumable_stack_usage.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestConsumableStackUsage(GameTestBase):

    def test_eat_from_stack(self):
        """Verify consuming one item from a stack reduces count."""
        # 1. Setup Stack
        self.world.item_templates["cookie"] = {
            "type": "Consumable", "name": "Cookie", "weight": 0.1, "stackable": True,
            "properties": {"uses": 1, "max_uses": 1, "effect_type": "heal", "effect_value": 1}
        }
        
        cookie = ItemFactory.create_item_from_template("cookie", self.world)
        if cookie:
            self.player.inventory.add_item(cookie, 5)
            
            # Check Initial
            self.assertEqual(self.player.inventory.count_item(cookie.obj_id), 5)
            
            # 2. Use Item via Command Processor to trigger inventory removal logic
            result = self.game.process_command("use cookie")
            
            # 3. Assert
            self.assertIsNotNone(result, "Command should return a result string.")
            if result:
                self.assertIn("consume", result)
                
            self.assertEqual(self.player.inventory.count_item(cookie.obj_id), 4)