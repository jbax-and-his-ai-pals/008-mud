# tests/singles/test_npc_dialogue_fallback.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCDialogueFallback(GameTestBase):

    def test_unknown_topic(self):
        """Verify NPC returns default response for unknown topics."""
        # Setup NPC with specific greeting but no "rumors"
        self.world.npc_templates["quiet_villager"] = {
            "name": "Bob", "dialog": {"greeting": "Hello."}, 
            "default_dialog": "Bob stares blankly."
        }
        
        npc = NPCFactory.create_npc_from_template("quiet_villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # Act
        response = npc.talk("politics")
        
        # Assert
        self.assertEqual(response, "Bob stares blankly.")
        
    def test_greeting_fallback(self):
        """Verify NPC returns default if greeting is missing."""
        self.world.npc_templates["rude_villager"] = {
            "name": "Rude", "dialog": {}, 
            "default_dialog": "Go away."
        }
        
        npc = NPCFactory.create_npc_from_template("rude_villager", self.world)
        if not npc: return
        
        # Act (No topic = greeting)
        response = npc.talk()
        
        # Assert
        self.assertEqual(response, "Go away.")