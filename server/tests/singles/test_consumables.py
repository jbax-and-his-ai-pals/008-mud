# tests/singles/test_consumables.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestConsumables(GameTestBase):
    def test_healing_potion(self):
        """Verify potions restore health and are removed."""
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.assertIsNotNone(potion)
        
        if potion:
            self.player.inventory.add_item(potion)
            self.player.max_health = 100
            self.player.health = 50 # Injure player
            
            # Act
            potion.use(self.player)
            
            # Assert
            self.assertGreater(self.player.health, 50, "Health should increase")
            self.assertEqual(potion.get_property("uses"), 0)

    def test_multi_use_item(self):
        """Verify items with >1 uses decrement correctly."""
        # Create a custom multi-use item (like Bread)
        bread = ItemFactory.create_item_from_template("item_hunk_bread", self.world)
        if bread:
            # Force stats for testing
            bread.update_property("uses", 2)
            bread.update_property("max_uses", 2)
            self.player.inventory.add_item(bread)
            
            # Use once
            msg = bread.use(self.player)
            self.assertEqual(bread.get_property("uses"), 1)
            self.assertIn("remaining", msg)
            
            # Use twice
            msg = bread.use(self.player)
            self.assertEqual(bread.get_property("uses"), 0)
            self.assertIn("used up", msg)

    def test_durability_loss(self):
        """Verify manual durability updates work on items."""
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            max_d = sword.get_property("max_durability")
            sword.update_property("durability", max_d)
            
            # Simulate a combat hit
            loss_amount = 5
            current = sword.get_property("durability")
            sword.update_property("durability", current - loss_amount)
            
            self.assertEqual(sword.get_property("durability"), max_d - loss_amount)