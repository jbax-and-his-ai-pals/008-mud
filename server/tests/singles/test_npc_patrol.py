# tests/singles/test_npc_patrol.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room
from engine.npcs.ai.movement import perform_patrol

class TestNPCPatrol(GameTestBase):

    def test_patrol_cycling(self):
        """Verify NPC moves to next patrol point upon arrival."""
        # 1. Setup Rooms (A <-> B)
        region = self.world.get_region("town")
        if not region: return
        
        room_a = Room("Point A", "Start", {"east": "point_b"}, obj_id="point_a")
        room_b = Room("Point B", "End", {"west": "point_a"}, obj_id="point_b")
        region.add_room("point_a", room_a)
        region.add_room("point_b", room_b)
        
        # 2. Setup NPC
        npc = NPCFactory.create_npc_from_template("town_guard", self.world)
        if npc:
            npc.current_region_id = "town"
            npc.current_room_id = "point_a"
            npc.home_region_id = "town" # Used for pathfinding context
            
            # Define Patrol Route: A -> B -> A
            npc.patrol_points = ["point_b", "point_a"]
            npc.patrol_index = 0
            npc.behavior_type = "patrol"
            
            self.world.add_npc(npc)
            
            # 3. Act: Perform Patrol (In 'point_a', target is 'point_b')
            # Should move East
            perform_patrol(npc, self.world, self.player)
            
            # 4. Assert: Moved to B
            self.assertEqual(npc.current_room_id, "point_b")
            
            # 5. Act: Arrived at target
            # Calling logic again should detect arrival and increment index, but NOT move immediately (cooldown usually)
            # However, perform_patrol logic says: if at target, increment index, return None.
            result = perform_patrol(npc, self.world, self.player)
            self.assertIsNone(result)
            self.assertEqual(npc.patrol_index, 1, "Should advance to next patrol point index.")
            self.assertEqual(npc.patrol_points[npc.patrol_index], "point_a")