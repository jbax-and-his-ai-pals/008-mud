# tests/singles/test_respawn_persistence.py
import os
import time
from tests.fixtures import GameTestBase

class TestRespawnPersistence(GameTestBase):
    
    TEST_SAVE = "test_respawn.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_respawn_queue_saves(self):
        """Verify dead unique NPCs persist in the respawn queue."""
        mgr = self.world.respawn_manager
        
        # 1. Add to Queue manually
        future_time = time.time() + 999.0
        entry = {
            "template_id": "guard",
            "instance_id": "unique_guard",
            "name": "Guard Bob",
            "home_region_id": "town",
            "home_room_id": "town_square",
            "respawn_time": future_time
        }
        mgr.respawn_queue.append(entry)
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Clear
        mgr.respawn_queue = []
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        
        # 5. Verify
        self.assertEqual(len(mgr.respawn_queue), 1)
        loaded_entry = mgr.respawn_queue[0]
        self.assertEqual(loaded_entry["instance_id"], "unique_guard")
        # Check time is roughly same (within float precision/serialization margin)
        self.assertAlmostEqual(loaded_entry["respawn_time"], future_time, places=2)