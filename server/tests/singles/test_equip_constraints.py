# tests/singles/test_equip_constraints.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestEquipConstraints(GameTestBase):
    def test_equip_wrong_slot(self):
        """Verify error when equipping item to invalid slot."""
        self.world.item_templates["boots"] = {
            "type": "Armor", "name": "Boots", "weight": 1, "value": 1,
            "properties": {"equip_slot": ["feet"], "defense": 1, "durability": 10}
        }
        boots = ItemFactory.create_item_from_template("boots", self.world)
        if boots:
            self.player.inventory.add_item(boots)
            
            res = self.game.process_command("equip boots to head")
            
            self.assertIsNotNone(res)
            if res:
                self.assertIn("cannot be equipped in the 'head'", res)
            self.assertIsNone(self.player.equipment["head"])