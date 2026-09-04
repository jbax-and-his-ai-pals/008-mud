# tests/singles/test_npc_follow_persistence.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCFollowPersistence(GameTestBase):

    def test_follow_toggle(self):
        """Verify follow command updates player state."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        
        # 1. Start Follow
        result_start = self.game.process_command(f"follow {npc.name}")
        
        self.assertIsNotNone(result_start)
        if result_start:
            self.assertIn("start following", result_start)
            
        self.assertEqual(self.player.follow_target, npc.obj_id)
        
        # 2. Stop Follow
        result_stop = self.game.process_command("follow stop")
        
        self.assertIsNotNone(result_stop)
        if result_stop:
            self.assertIn("stop following", result_stop)
            
        self.assertIsNone(self.player.follow_target)