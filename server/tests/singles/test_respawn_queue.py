# tests/singles/test_respawn_queue.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestRespawnQueue(GameTestBase):

    def test_respawn_timer(self):
        """Verify NPCs respawn only after time elapses."""
        # 1. Setup Manager
        mgr = self.world.respawn_manager
        
        # 2. Create and "Kill" NPC
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="dead_goblin")
        if npc:
            npc.home_region_id = "town"
            npc.home_room_id = "town_square"
            
            # Manually add to queue with specific time
            current_time = time.time()
            respawn_time = current_time + 100.0
            
            data = {
                "template_id": "goblin",
                "instance_id": "dead_goblin",
                "name": "Goblin",
                "home_region_id": "town",
                "home_room_id": "town_square",
                "respawn_time": respawn_time
            }
            mgr.respawn_queue.append(data)
            
            # 3. Update Early (Should not spawn)
            mgr.update(current_time + 50.0)
            self.assertNotIn("dead_goblin", self.world.npcs)
            self.assertEqual(len(mgr.respawn_queue), 1)
            
            # 4. Update Late (Should spawn)
            mgr.update(current_time + 101.0)
            self.assertIn("dead_goblin", self.world.npcs)
            self.assertEqual(len(mgr.respawn_queue), 0)
            
            # Verify location reset
            spawned = self.world.get_npc("dead_goblin")
            if spawned:
                self.assertEqual(spawned.current_room_id, "town_square")