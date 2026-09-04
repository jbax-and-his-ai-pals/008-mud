# tests/singles/test_npc_state_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCStatePersistence(GameTestBase):
    
    TEST_SAVE = "test_npc_persist.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_npc_health_save(self):
        """Verify NPC health persists through save/load."""
        # 1. Setup NPC
        npc = NPCFactory.create_npc_from_template("town_guard", self.world, instance_id="persist_guard")
        if not npc: return
        
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        npc.max_health = 100
        npc.health = 50 # Injured
        
        self.world.add_npc(npc)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Clear World
        self.world.npcs = {}
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        
        # 5. Assert
        loaded_npc = self.world.get_npc("persist_guard")
        self.assertIsNotNone(loaded_npc)
        if loaded_npc:
            self.assertEqual(loaded_npc.health, 50)
            self.assertEqual(loaded_npc.max_health, 100)