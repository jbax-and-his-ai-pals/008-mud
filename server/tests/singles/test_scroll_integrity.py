# tests/singles/test_scroll_integrity.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestScrollIntegrity(GameTestBase):
    def test_scroll_invalid_spell(self):
        """Verify scroll with bad spell ID doesn't crash or consume."""
        self.world.item_templates["bad_scroll"] = {
            "type": "Consumable", "name": "Glitch Scroll", "weight": 0.1, "value": 1,
            "properties": {"effect_type": "learn_spell", "spell_to_learn": "missing_no", "uses": 1}
        }
        scroll = ItemFactory.create_item_from_template("bad_scroll", self.world)
        if scroll:
            self.player.inventory.add_item(scroll)
            
            res = self.game.process_command("use Glitch Scroll")
            
            self.assertIsNotNone(res)
            if res:
                self.assertIn("secrets of 'missing_no' seem non-existent", res) 
            
            # Should not consume
            self.assertEqual(self.player.inventory.count_item(scroll.obj_id), 1)