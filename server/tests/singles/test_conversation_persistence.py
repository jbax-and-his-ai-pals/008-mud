# tests/singles/test_conversation_persistence.py
import os
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestConversationPersistence(GameTestBase):
    
    TEST_SAVE = "test_conv_save.json"

    def tearDown(self):
        if os.path.exists(os.path.join("data", "saves", self.TEST_SAVE)):
            try: os.remove(os.path.join("data", "saves", self.TEST_SAVE))
            except: pass
        super().tearDown()

    def test_vocabulary_and_history(self):
        """Verify known topics and NPC interaction history persist."""
        npc = NPCFactory.create_npc_from_template("villager", self.world, instance_id="talkative_tom")
        if npc: self.world.add_npc(npc)
        
        # 1. Modify State
        # Learn a new global topic
        self.player.conversation.learn_vocabulary("ancient_history")
        # Mark specific topic as discussed with Tom
        self.player.conversation.mark_discussed("talkative_tom", "job")
        
        # 2. Save
        self.world.save_game(self.TEST_SAVE)
        
        # 3. Wipe
        self.player.conversation.vocabulary = set()
        self.player.conversation.npc_history = {}
        
        # 4. Load
        self.world.load_save_game(self.TEST_SAVE)
        loaded = self.world.player
        
        # 5. Verify
        if loaded:
            # Check Global Vocab
            self.assertTrue(loaded.conversation.is_in_vocabulary("ancient_history"))
            
            # Check Specific History
            self.assertTrue(loaded.conversation.has_discussed("talkative_tom", "job"))
            # Ensure we didn't magically discuss it with someone else
            self.assertFalse(loaded.conversation.has_discussed("other_npc", "job"))