# tests/singles/test_knowledge_history.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestKnowledgeHistory(GameTestBase):

    def test_conversation_state_transition(self):
        """Verify topics move to 'discussed' set after being asked."""
        # 1. Setup NPC
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if npc and self.player:
            self.world.add_npc(npc)
            npc_id = npc.obj_id
            
            # 2. Check Initial State
            self.assertFalse(self.player.conversation.has_discussed(npc_id, "job"))
            
            # 3. Use 'ask' command
            # This triggers: player.conversation.mark_discussed(npc_id, topic_id)
            self.game.process_command(f"ask {npc.name} job")
            
            # 4. Assert State Updated
            self.assertTrue(self.player.conversation.has_discussed(npc_id, "job"))
            
            # Verify the UI logic (get_topics_for_npc) would now see it as 'asked'
            unasked, asked = self.game.knowledge_manager.get_topics_for_npc(npc, self.player)
            self.assertIn("job", asked)
            self.assertNotIn("job", unasked)