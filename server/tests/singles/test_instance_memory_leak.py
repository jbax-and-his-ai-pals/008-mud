# tests/singles/test_instance_memory_leak.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestInstanceMemoryLeak(GameTestBase):

    def test_npcs_removed_from_global_dict(self):
        """Verify NPCs inside an instance are removed from engine.world.npcs on cleanup."""
        # 1. Mock Quest Completion
        quest_id = "test_leak"
        region_id = "instance_test_leak"
        
        self.player.runtime_state.quests.completed[quest_id] = {
            "instance_id": quest_id,
            "instance_region_id": region_id,
            "entry_point": {"region_id": "town", "room_id": "town_square", "exit_command": "portal"}
        }
        
        # 2. Create Instance Region
        from engine.world.region import Region
        region = Region("Leak Test", "Test", obj_id=region_id)
        self.world.add_region(region_id, region)
        
        # 3. Add NPC to Instance
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        if npc:
            npc.current_region_id = region_id
            self.world.add_npc(npc)
            npc_id = npc.obj_id
            
            self.assertIn(npc_id, self.world.npcs)
            
            # 4. Cleanup
            self.world.cleanup_quest_region(quest_id)
            
            # 5. Assert Gone
            self.assertNotIn(npc_id, self.world.npcs, "NPC should be removed from global registry.")
            self.assertNotIn(region_id, self.world.regions)
