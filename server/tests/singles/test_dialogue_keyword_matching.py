# tests/singles/test_dialogue_keyword_matching.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestDialogueKeywordMatching(GameTestBase):

    def setUp(self):
        super().setUp()
        # Setup a topic with specific keywords
        self.km = self.game.knowledge_manager
        self.km.topics["ancient_history"] = {
            "display_name": "History",
            "keywords": ["old times", "past", "legends"],
            "responses": [{"text": "It was a dark time.", "conditions": {}, "priority": 1}]
        }

    def test_keyword_resolution(self):
        """Verify synonyms map to the correct topic."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # 1. Ask using keyword "legends"
        response = self.game.process_command(f"ask {npc.name} legends")
        
        self.assertIsNotNone(response)
        if response:
            self.assertIn("dark time", response)
            
    def test_partial_keyword_resolution(self):
        """Verify multi-word keywords work."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # 1. Ask using "old times"
        response = self.game.process_command(f"ask {npc.name} old times")
        
        self.assertIsNotNone(response)
        if response:
            self.assertIn("dark time", response)