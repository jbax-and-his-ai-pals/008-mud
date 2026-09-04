# tests/singles/test_drop_frees_weight.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestDropFreesWeight(GameTestBase):

    def test_weight_update_on_drop(self):
        """Verify inventory weight decreases when items are dropped."""
        # 1. Create Heavy Item (10.0 weight)
        self.world.item_templates["heavy_bar"] = {"type": "Item", "name": "Lead Bar", "weight": 10.0}
        
        bar = ItemFactory.create_item_from_template("heavy_bar", self.world)
        if bar:
            self.player.inventory.add_item(bar)
            
            start_weight = self.player.inventory.get_total_weight()
            self.assertEqual(start_weight, 10.0)
            
            # 2. Drop Item
            self.game.process_command("drop Lead Bar")
            
            # 3. Verify Weight
            end_weight = self.player.inventory.get_total_weight()
            self.assertEqual(end_weight, 0.0, "Weight should return to 0 after drop.")