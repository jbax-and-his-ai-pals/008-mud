# tests/singles/test_world_generation.py
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator

class TestWorldGeneration(GameTestBase):
    
    def test_generate_region_structure(self):
        """Verify dynamic region generation creates valid rooms and exits."""
        generator = RegionGenerator(self.world)
        
        # 1. Generate
        # "caves" is a standard theme in dynamic_themes.json
        result = generator.generate_region("caves", num_rooms=5)
        
        self.assertIsNotNone(result, "Generation failed.")
        if result:
            region, entry_id = result
            
            # 2. Verify Region
            self.assertIsNotNone(region.obj_id)
            self.assertTrue(region.obj_id.startswith("dynamic_"))
            
            # 3. Verify Rooms
            self.assertEqual(len(region.rooms), 5, "Should generate exactly 5 rooms.")
            self.assertIn(entry_id, region.rooms)
            
            # 4. Verify Connectivity (Entry should have at least one exit)
            entry_room = region.get_room(entry_id)
            self.assertIsNotNone(entry_room, "Entry room ID returned by generator not found in region.")
            
            # Explicit check for type safety
            if entry_room:
                self.assertTrue(len(entry_room.exits) > 0, "Entry room must have exits.")
            
    def test_invalid_theme(self):
        """Verify generator handles missing themes gracefully."""
        generator = RegionGenerator(self.world)
        result = generator.generate_region("non_existent_theme", 5)
        self.assertIsNone(result)