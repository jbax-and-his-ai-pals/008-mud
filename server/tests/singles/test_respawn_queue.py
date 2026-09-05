# tests/singles/test_respawn_queue.py
import time
from unittest.mock import patch

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

    def test_npc_creation_failure_leaves_entry_in_queue(self):
        mgr = self.world.respawn_manager
        data = {
            "template_id": "goblin", "instance_id": "failed_goblin", "name": "Goblin",
            "home_region_id": "town", "home_room_id": "town_square",
            "respawn_time": time.time() - 1.0,
        }
        mgr.respawn_queue.append(data)

        with patch(
            "engine.world.respawn_manager.NPCFactory.create_npc_from_template", return_value=None,
        ):
            messages = mgr.update(time.time())

        self.assertEqual([], messages)
        self.assertIn(data, mgr.respawn_queue)

    def test_no_player_in_room_produces_no_message(self):
        mgr = self.world.respawn_manager
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        data = {
            "template_id": "goblin", "instance_id": "quiet_goblin", "name": "Goblin",
            "home_region_id": "town", "home_room_id": "town_square",
            "respawn_time": time.time() - 1.0,
        }
        mgr.respawn_queue.append(data)

        messages = mgr.update(time.time())

        self.assertEqual([], messages)
        self.assertIn("quiet_goblin", self.world.npcs)

    def test_first_non_matching_player_is_skipped_in_favor_of_a_later_match(self):
        mgr = self.world.respawn_manager
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"  # does not match home room

        class _StubPlayer:
            obj_id = "stub_watcher"
            current_region_id = "town"
            current_room_id = "town_square"  # matches home room

        stub = _StubPlayer()
        self.world.players[stub.obj_id] = stub
        try:
            data = {
                "template_id": "goblin", "instance_id": "watched_goblin", "name": "Goblin",
                "home_region_id": "town", "home_room_id": "town_square",
                "respawn_time": time.time() - 1.0,
            }
            mgr.respawn_queue.append(data)

            messages = mgr.update(time.time())
        finally:
            del self.world.players[stub.obj_id]

        self.assertEqual(1, len(messages))
        location, message = messages[0]
        self.assertEqual(("town", "town_square"), location)
        self.assertIn("has returned", message)