# tests/singles/test_npc_loot_quantity.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCLootQuantity(GameTestBase):

    def test_loot_quantity_range(self):
        """Verify loot drops respect the quantity range format [min, max]."""
        self.world.item_templates["gold_dust"] = {"type": "Item", "name": "gold dust", "stackable": True}
        self.world.npc_templates["wealthy_goblin"] = {
            "name": "Goblin", "faction": "hostile", "level": 1,
            "loot_table": {
                "gold_dust": {"chance": 1.0, "quantity": [5, 10]}
            }
        }
        
        goblin = NPCFactory.create_npc_from_template("wealthy_goblin", self.world)
        self.assertIsNotNone(goblin)
        
        if goblin:
            goblin.current_region_id = "town"
            goblin.current_room_id = "town_square"
            
            with patch('random.randint', return_value=10):
                dropped_items = goblin.die(self.world)
                
            self.assertEqual(len(dropped_items), 10)
            
            room_items = self.world.get_items_in_room("town", "town_square")
            dust_count = sum(1 for i in room_items if i.name == "gold dust")
            self.assertEqual(dust_count, 10)