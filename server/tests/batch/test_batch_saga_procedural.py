# tests/batch/test_batch_saga_procedural.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestBatchSagaProcedural(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.world.item_templates["item_iron_sword"] = {"type": "Weapon", "name": "Iron Sword"}
        self.world.npc_templates["goblin"] = {"name": "Goblin", "faction": "hostile"}
        self.world.npc_templates["wolf"] = {"name": "Wolf", "faction": "hostile"}
        self.world.npc_templates["giant_rat"] = {"name": "Rat", "faction": "hostile"}
        
        # USE NEW ATTRIBUTE: quest_templates
        self.world.quest_manager.quest_templates["saga_procedural_hunt"] = {
            "title": "Hunt", "type": "saga",
            "generate_rewards": {
                "xp_range": [100, 200],
                "gold_range": [50, 100],
                "generate_item": {
                    "base_template_id": "item_iron_sword",
                    "level": 1,
                    "rarity": 0.5
                }
            },
            "stages": [{
                "stage_index": 0,
                "objective": {
                    "type": "group_kill",
                    "targets_config": {
                        "monster_pool": ["goblin", "wolf", "giant_rat"],
                        "total_types": 2,
                        "count_per_type_range": [1, 1]
                    }
                },
                "turn_in_config": {"npc_pool_faction": "friendly"}
            }]
        }

    def test_procedural_saga_targets(self):
        """Verify grouped kill objectives track progress correctly."""
        qm = self.world.quest_manager
        # USE NEW METHOD: start_quest
        success = qm.start_quest("saga_procedural_hunt", self.player)
        self.assertTrue(success)
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active[inst_id]
        
        objective = quest["stages"][0]["objective"]
        
        self.assertEqual(objective["type"], "group_kill")
        self.assertIn("targets", objective, "Targets dict should be generated from config.")
        self.assertEqual(len(objective["targets"]), 2)

    def test_procedural_rewards_generation(self):
        """Verify rewards are generated and not static."""
        qm = self.world.quest_manager
        
        with patch('random.random', return_value=0.0):
             # USE NEW METHOD: start_quest
             success = qm.start_quest("saga_procedural_hunt", self.player)
             
        self.assertTrue(success)
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        q1 = self.player.runtime_state.quests.active[inst_id]
        rewards = q1["rewards"]
        
        self.assertIn("xp", rewards)
        self.assertIn("gold", rewards)
        
        if "generated_item_data" in rewards:
            item_data = rewards["generated_item_data"]
            self.assertIn("name", item_data)
            generated_name = item_data.get("name", "").lower()
            self.assertNotEqual(generated_name, "iron sword")

    def test_turn_in_npc_resolution(self):
        """Verify the turn-in NPC is resolved dynamically."""
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc: 
             npc.current_region_id = "town"
             npc.faction = "friendly"
             self.world.add_npc(npc)
        
        qm = self.world.quest_manager
        # USE NEW METHOD: start_quest
        qm.start_quest("saga_procedural_hunt", self.player)
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active[inst_id]
        
        turn_in_id = quest["stages"][0].get("turn_in_id")
        self.assertIsNotNone(turn_in_id)
        
        if turn_in_id != "quest_board":
             chosen_npc = self.world.get_npc(turn_in_id)
             self.assertIsNotNone(chosen_npc, f"Chosen NPC {turn_in_id} not found in world.")
             if chosen_npc:
                 self.assertEqual(chosen_npc.faction, "friendly")
