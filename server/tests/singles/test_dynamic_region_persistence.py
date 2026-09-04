# tests/singles/test_dynamic_region_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator

class TestDynamicRegionPersistence(GameTestBase):
    
    TEST_SAVE = "test_dynamic_save.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_dynamic_region_save_load(self):
        """Verify procedurally generated regions persist after loading."""
        # 1. Generate a Region
        generator = RegionGenerator(self.world)
        result = generator.generate_region("caves", num_rooms=5)
        
        self.assertIsNotNone(result)
        if result:
            new_region, entry_id = result
            region_id = new_region.obj_id
            self.world.add_region(region_id, new_region)
            
            # 2. Move player there
            self.world.current_region_id = region_id
            self.world.current_room_id = entry_id
            self.player.current_region_id = region_id
            self.player.current_room_id = entry_id
            
            # 3. Save
            self.world.save_game(self.TEST_SAVE)
            
            # 4. Clear World
            self.world.regions = {} 
            
            # 5. Load
            success, _, _ = self.world.load_save_game(self.TEST_SAVE)
            self.assertTrue(success)
            
            # 6. Verify Region Exists
            self.assertIn(region_id, self.world.regions, "Dynamic region should be loaded.")
            loaded_region = self.world.regions[region_id]
            self.assertEqual(len(loaded_region.rooms), 5, "Room count should be preserved.")
            
            # 7. Verify Player Location
            # After load, self.player (from fixture) might be stale, use self.world.player
            self.assertIsNotNone(self.world.player)
            if self.world.player:
                self.assertEqual(self.world.player.current_region_id, region_id)