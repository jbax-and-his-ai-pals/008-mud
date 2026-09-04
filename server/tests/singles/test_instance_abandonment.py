# tests/singles/test_instance_abandonment.py
from tests.fixtures import GameTestBase

class TestInstanceAbandonment(GameTestBase):

    def test_cleanup_removes_region_and_npcs(self):
        """Verify cleaning up a quest region removes it from the world."""
        # 1. Setup Data
        quest_id = "test_cleanup_quest"
        quest_data = {
            "instance_id": quest_id,
            "instance_region_id": "instance_to_delete",
            "entry_point": {
                "region_id": "town", "room_id": "town_square", "exit_command": "enter_portal"
            }
        }
        
        # Mock the quest being in completed log (where cleanup looks)
        self.player.runtime_state.quests.completed[quest_id] = quest_data
        
        # 2. Inject Dummy Region and NPC
        from engine.world.region import Region
        region = Region("Doom Instance", "Doom", obj_id="instance_to_delete")
        self.world.add_region("instance_to_delete", region)
        
        from engine.npcs.npc_factory import NPCFactory
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="doom_goblin")
        if npc:
            npc.current_region_id = "instance_to_delete"
            self.world.add_npc(npc)
            
        # Verify setup
        self.assertIn("instance_to_delete", self.world.regions)
        self.assertIn("doom_goblin", self.world.npcs)
        
        # 3. Act: Cleanup
        self.world.cleanup_quest_region(quest_id)
        
        # 4. Assert
        self.assertNotIn("instance_to_delete", self.world.regions)
        self.assertNotIn("doom_goblin", self.world.npcs)
