# tests/singles/test_npc_loot_rarity.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCLootRarity(GameTestBase):

    def setUp(self):
        super().setUp()
        self.world.item_templates["common_scrap"] = {"type": "Junk", "name": "Scrap"}
        self.world.item_templates["rare_gem"] = {"type": "Gem", "name": "Rare Gem"}
        
        self.world.npc_templates["loot_bag"] = {
            "name": "Loot Bag", "faction": "neutral", "health": 1,
            "loot_table": {
                "common_scrap": {"chance": 1.0}, # 100%
                "rare_gem": {"chance": 0.1}      # 10%
            }
        }

    def test_rare_drop_failure(self):
        """Verify rare item does not drop on high roll."""
        npc = NPCFactory.create_npc_from_template("loot_bag", self.world)
        if not npc: return
        npc.current_region_id = "town"; npc.current_room_id = "town_square"
        
        # Patch random.random to return 0.5
        # Scrap (1.0) > 0.5 -> Drop
        # Gem (0.1) < 0.5 -> No Drop
        with patch('random.random', return_value=0.5):
            dropped = npc.die(self.world)
            
        names = [i.name for i in dropped]
        self.assertIn("Scrap", names)
        self.assertNotIn("Rare Gem", names)

    def test_rare_drop_success(self):
        """Verify rare item drops on low roll."""
        npc = NPCFactory.create_npc_from_template("loot_bag", self.world)
        if not npc: return
        npc.current_region_id = "town"; npc.current_room_id = "town_square"
        
        # Patch random.random to return 0.05
        # Scrap (1.0) > 0.05 -> Drop
        # Gem (0.1) > 0.05 -> Drop
        with patch('random.random', return_value=0.05):
            dropped = npc.die(self.world)
            
        names = [i.name for i in dropped]
        self.assertIn("Scrap", names)
        self.assertIn("Rare Gem", names)