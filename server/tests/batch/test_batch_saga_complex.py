# tests/batch/test_batch_saga_complex.py
import time
from unittest.mock import patch, MagicMock
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room

class TestBatchSagaComplex(GameTestBase):

    def setUp(self):
        super().setUp()
        
        clean_town = Region("Town", "x", obj_id="town")
        clean_town.add_room("town_square", Room("Square", "x", obj_id="town_square"))
        self.world.regions["town"] = clean_town 
        
        self.world.npc_templates["bandit_leader"] = {"name": "Bandit", "faction": "hostile", "level": 3}
        
        # USE NEW ATTRIBUTE: quest_templates
        self.world.quest_manager.quest_templates["saga_bandit_king_test"] = {
            "title": "Complex Test",
            "type": "saga",
            "procedural_regions": [
                { 
                    "id_key": "camp", 
                    "theme": "forest", 
                    "rooms": 2, 
                    "entry_point": { "region": "town", "room": "town_square" } 
                }
            ],
            "stages": [
                {
                    "stage_index": 0, "description": "Scout.", "turn_in_id": "guard",
                    "objective": { "type": "scout", "target_region": "{camp}" }
                },
                {
                    "stage_index": 1, "description": "Negotiate.", "turn_in_id": "bandit_leader",
                    "objective": {
                        "type": "negotiate", "target_npc_id": "bandit_leader",
                        "skill": "diplomacy", "difficulty": 50,
                        "choices": {
                            "success": { "next_stage": 3 },
                            "fail": { "next_stage": 2, "description": "Negotiation FAIL" }
                        }
                    }
                },
                {"stage_index": 2, "description": "Fail", "objective": {}, "turn_in_id": "guard"},
                {"stage_index": 3, "description": "Success", "objective": {}, "turn_in_id": "guard"}
            ]
        }

    def test_saga_region_generation(self):
        """Verify new region is generated and linked."""
        qm = self.world.quest_manager
        
        # Correctly mock RegionGenerator which is used inside generator.py
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockRegionGen:
            mock_gen_instance = MockRegionGen.return_value
            generated_region = Region("Mock Forest", "Trees.", obj_id="gen_forest_1")
            generated_region.add_room("start_node", Room("Start", "x", obj_id="start_node"))
            mock_gen_instance.generate_region.return_value = (generated_region, "start_node")
            
            # USE NEW METHOD: start_quest
            success = qm.start_quest("saga_bandit_king_test", self.player)
        
        self.assertTrue(success, "Failed to start saga")
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active[inst_id]
        
        self.assertIn("generated_region_ids", quest)
        gen_id = quest["generated_region_ids"][0]
        self.assertEqual(gen_id, "gen_forest_1")
        
        self.assertIn(gen_id, self.world.regions)
        
        town = self.world.get_region("town")
        if town:
            sq = town.get_room("town_square")
            if sq:
                self.assertIn("enter_quest", sq.exits, f"Exits found: {sq.exits}")
                self.assertEqual(sq.exits["enter_quest"], "gen_forest_1:start_node")

    def test_negotiation_mechanic(self):
        """Verify negotiation skill check branches logic."""
        qm = self.world.quest_manager
        
        with patch("engine.core.quest_generation.generator.RegionGenerator") as MockRegionGen:
            mock_gen_instance = MockRegionGen.return_value
            dummy_reg = Region("R", "D", obj_id="d_reg")
            dummy_reg.add_room("r", Room("r", "d", obj_id="r"))
            mock_gen_instance.generate_region.return_value = (dummy_reg, "r")
            
            # USE NEW METHOD: start_quest
            qm.start_quest("saga_bandit_king_test", self.player)
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active[inst_id]
        
        quest["current_stage_index"] = 1
        
        bandit = NPCFactory.create_npc_from_template("bandit_leader", self.world)
        if bandit:
            self.world.add_npc(bandit)
            bandit.current_region_id = self.player.current_region_id
            bandit.current_room_id = self.player.current_room_id
            
            with patch('random.randint', return_value=1):
                from engine.commands.interaction.npcs import _handle_quest_dialogue
                res = _handle_quest_dialogue(self.player, bandit, self.world)
            
            self.assertIn("Negotiation FAIL", res)
            self.assertEqual(self.player.runtime_state.quests.active[inst_id]["current_stage_index"], 2)
