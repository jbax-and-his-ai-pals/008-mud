# tests/singles/test_map_generation_parameters.py
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator

class TestMapGenerationParameters(GameTestBase):

    def test_room_count_respect(self):
        """Verify generator creates exactly the requested number of rooms."""
        generator = RegionGenerator(self.world)
        
        # Request 10 rooms
        result = generator.generate_region("caves", 10)
        
        self.assertIsNotNone(result)
        if result:
            region, _ = result
            self.assertEqual(len(region.rooms), 10)

        # Request 5 rooms
        result_small = generator.generate_region("forest", 5)
        if result_small:
            region_small, _ = result_small
            self.assertEqual(len(region_small.rooms), 5)