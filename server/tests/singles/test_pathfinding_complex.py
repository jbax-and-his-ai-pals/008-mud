# tests/singles/test_pathfinding_complex.py
from typing import List, Optional
from tests.fixtures import GameTestBase
from engine.world.room import Room
from engine.world.region import Region

class TestPathfindingComplex(GameTestBase):

    def test_circular_path(self):
        """Verify pathfinding handles loops and finds shortest route."""
        # Graph Topology:
        # A -> B (East) -> C (East)  [Length: 2]
        # A -> D (South) -> C (West) [Length: 2]
        
        region: Optional[Region] = self.world.get_region("town")
        self.assertIsNotNone(region, "Town region should exist")
        if not region: return

        # Setup Graph
        region.add_room("A", Room("A", "", {"east": "B", "south": "D"}, obj_id="A"))
        region.add_room("B", Room("B", "", {"west": "A", "east": "C"}, obj_id="B"))
        region.add_room("C", Room("C", "", {"west": "B", "east": "D"}, obj_id="C"))
        # Fix: Changed second "north" to "west" to avoid key collision
        region.add_room("D", Room("D", "", {"north": "A", "west": "C"}, obj_id="D")) 

        # Find Path A -> C
        path: Optional[List[str]] = self.world.find_path("town", "A", "town", "C")
        
        self.assertIsNotNone(path, "Path should be found")
        if path is not None:
            # Shortest path is 2 steps (either [East, East] or [South, West])
            self.assertEqual(len(path), 2)

    def test_unreachable(self):
        """Verify None returned for disconnected rooms."""
        region: Optional[Region] = self.world.get_region("town")
        self.assertIsNotNone(region)
        if not region: return

        # Add isolated room
        region.add_room("Island", Room("Island", "", {}, obj_id="Island"))
        
        path: Optional[List[str]] = self.world.find_path("town", "town_square", "town", "Island")
        self.assertIsNone(path, "Path to isolated room should be None")