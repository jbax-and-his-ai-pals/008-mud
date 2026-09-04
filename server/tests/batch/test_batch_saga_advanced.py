# tests/batch/test_batch_saga_advanced.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room

class TestBatchSagaAdvanced(GameTestBase):
    
    def setUp(self):
        super().setUp()
        
        # USE NEW ATTRIBUTE: quest_templates
        self.world.quest_manager.quest_templates["saga_branching_diplomacy"] = {
            "title": "The Goblin Problem",
            "type": "saga",
            "stages": [
                {
                    "stage_index": 0,
                    "description": "Deal with the Goblin Emissary.",
                    "objective": {
                        "type": "dialogue_choice",
                        "npc_template_id": "goblin_emissary",
                        "choices": {
                            "attack": { "next_stage": 1, "description": "You chose violence." },
                            "negotiate": { "next_stage": 2, "description": "You chose peace." }
                        }
                    },
                    "turn_in_id": "village_elder",
                    "start_dialogue": "Deal with him."
                },
                {
                    "stage_index": 1,
                    "description": "Kill the Goblin Warlord.",
                    "objective": { "type": "kill", "target_template_id": "goblin_warlord", "required_quantity": 1 },
                    "turn_in_id": "village_elder",
                    "completion_dialogue": "Violence begets peace."
                },
                {
                    "stage_index": 2,
                    "description": "Collect tribute.",
                    "objective": { "type": "fetch", "item_id": "item_shiny_rock", "required_quantity": 5 },
                    "turn_in_id": "village_elder",
                    "completion_dialogue": "A strange price for peace."
                }
            ]
        }

        self.world.quest_manager.quest_templates["saga_ancient_secrets"] = {
            "title": "Secrets of the Past",
            "type": "saga",
            "stages": [
                {
                    "stage_index": 0,
                    "description": "Scout the Ancient Ruins.",
                    "objective": {
                        "type": "scout",
                        "target_region": "ruins",
                        "target_room_keywords": ["library", "scriptorium"]
                    },
                    "turn_in_id": "curator",
                    "completion_dialogue": "Excellent finding."
                }
            ]
        }
        
        if "ruins" not in self.world.regions:
            ruins = Region("Ruins", "Old place", obj_id="ruins")
            ruins.add_room("library", Room("Library", "Books.", obj_id="library"))
            self.world.add_region("ruins", ruins)

    def test_saga_branching(self):
        """Verify dialogue choice changes saga stage."""
        qm = self.world.quest_manager
        q_id = "saga_branching_diplomacy"
        
        # USE NEW METHOD: start_quest
        success = qm.start_quest(q_id, self.player)
        self.assertTrue(success, "Failed to start branching saga.")
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]

        # USE NEW METHOD: advance_quest_stage
        res = qm.advance_quest_stage(self.player, inst_id, choice_id="negotiate")
        
        self.assertIsNotNone(res)
        if res:
             self.assertIn("chose peace", res)
        
        quest = self.player.runtime_state.quests.active.get(inst_id)
        self.assertIsNotNone(quest)
        if quest:
            self.assertEqual(quest["current_stage_index"], 2)

    def test_scout_objective(self):
        """Verify entering target room completes objective."""
        qm = self.world.quest_manager
        q_id = "saga_ancient_secrets"
        
        # USE NEW METHOD: start_quest
        success = qm.start_quest(q_id, self.player)
        self.assertTrue(success, "Failed to start scout saga.")
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active.get(inst_id)
        
        self.assertIsNotNone(quest)
        if not quest: return

        obj = qm.get_active_objective(quest)
        if not obj: self.fail("No objective found")
        
        target_room = obj.get("target_room_id")
        self.assertNotEqual(target_room, "unknown", "Scouting objective failed to find a valid target room.")
        
        self.player.current_region_id = "ruins"
        self.player.current_room_id = target_room
        
        qm.handle_room_entry(self.player)
        
        self.assertEqual(quest["state"], "ready_to_complete")
