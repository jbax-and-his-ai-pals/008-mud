# tests/singles/test_knowledge_discovery.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestKnowledgeDiscovery(GameTestBase):

    def test_learning_on_mention(self):
        """Verify player vocabulary updates when a topic is mentioned in text."""
        km = self.game.knowledge_manager
        km.topics["secret_cave"] = {"display_name": "Secret Cave", "keywords": ["cave"]}
        
        # Initial state: Topic is unknown
        self.assertFalse(self.player.conversation.is_in_vocabulary("secret_cave"))
        
        # Act: Pass text containing the keyword through the highlighter
        raw_text = "I saw a strange cave to the north."
        km.parse_and_highlight(raw_text, self.player)
        
        # Assert: Player now "knows" the topic exists
        self.assertTrue(self.player.conversation.is_in_vocabulary("secret_cave"))

    def test_topic_reveal_by_npc(self):
        """Verify NPC mention reveals the topic specifically for that NPC's UI."""
        km = self.game.knowledge_manager
        km.topics["job"] = {"display_name": "Job", "keywords": []}
        
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc and self.player:
            npc_id = npc.obj_id
            # Act: Highlight text originating from this NPC
            km.parse_and_highlight("I'm looking for a job.", self.player, source_npc=npc)
            
            # Assert: The topic is now 'revealed' for this specific NPC
            self.assertTrue(self.player.conversation.is_revealed(npc_id, "job"))