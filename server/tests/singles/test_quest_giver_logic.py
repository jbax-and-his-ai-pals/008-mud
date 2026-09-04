# tests/singles/test_quest_giver_logic.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestGiverLogic(GameTestBase):
    
    def test_npc_quest_interests(self):
        """Verify that quest board replenishment respects NPC interests."""
        qm = self.world.quest_manager
        
        # Setup specific interest
        self.world.npc_templates["quest_npc"] = {
            "name": "Quest NPC", "faction": "friendly",
            "properties": { "can_give_generic_quests": True, "quest_interests": ["kill"] }
        }
        self.world.npc_templates["target_mob"] = {"name": "Target Mob", "faction": "hostile", "level": 1}
        
        npc = NPCFactory.create_npc_from_template("quest_npc", self.world)
        if npc:
            npc.current_region_id = "town"
            self.world.add_npc(npc)
            
        qm.npc_interests["quest_npc"] = ["kill"]
        self.world.quest_board = []
        
        # Correctly patch QUEST_TYPES_ALL in the manager module
        with patch('engine.core.quests.manager.QUEST_TYPES_ALL', ["kill"]):
            qm.ensure_initial_quests()
        
        # Assert found kill quest
        found_kill = False
        for q in self.world.quest_board:
            stages = q.get("stages", [])
            if stages:
                # Check first stage objective
                if stages[0]["objective"].get("type") == "kill":
                    found_kill = True
                    break
                    
        self.assertTrue(found_kill, "Quest board should have generated a kill quest.")
