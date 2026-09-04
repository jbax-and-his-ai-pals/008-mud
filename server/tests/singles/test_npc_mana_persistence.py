# tests/singles/test_npc_mana_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCManaPersistence(GameTestBase):
    
    TEST_SAVE = "test_npc_mana.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_mana_state_saves(self):
        """Verify NPC mana and max_mana persist."""
        npc = NPCFactory.create_npc_from_template("wandering_mage", self.world, instance_id="mage_1")
        if not npc: return
        
        npc.max_mana = 100
        npc.mana = 20 # Low mana
        self.world.add_npc(npc)
        
        # Save
        self.world.save_game(self.TEST_SAVE)
        
        # Clear
        self.world.npcs = {}
        
        # Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded = self.world.get_npc("mage_1")
        
        self.assertIsNotNone(loaded)
        if loaded:
            self.assertEqual(loaded.mana, 20)
            self.assertEqual(loaded.max_mana, 100)