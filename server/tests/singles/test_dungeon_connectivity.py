# tests/singles/test_dungeon_connectivity.py
from collections import deque
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator

class TestDungeonConnectivity(GameTestBase):

    def test_generated_rooms_reachable(self):
        """Verify all rooms in a generated region are reachable from the entrance."""
        generator = RegionGenerator(self.world)
        result = generator.generate_region("caves", num_rooms=10)
        
        self.assertIsNotNone(result)
        if result:
            region, entry_id = result
            
            # BFS traversal
            visited = set()
            queue = deque([entry_id])
            visited.add(entry_id)
            
            count = 0
            while queue:
                curr_id = queue.popleft()
                count += 1
                room = region.get_room(curr_id)
                
                if room:
                    for exit_dir, target_id in room.exits.items():
                        # Exits might be "region:room" or just "room"
                        # Generator creates internal links as just IDs usually, 
                        # but we should handle split just in case
                        tid = target_id.split(":")[-1]
                        
                        if tid in region.rooms and tid not in visited:
                            visited.add(tid)
                            queue.append(tid)
            
            # Assert
            self.assertEqual(count, len(region.rooms), "All generated rooms should be reachable from the entry.")