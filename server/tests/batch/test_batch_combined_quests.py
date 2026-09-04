# tests/batch/test_batch_combined_quests.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestBatchCombinedQuests(GameTestBase):

    def test_quest_fetch_stack_split(self):
        """Verify turning in a quest consumes only the required amount from a stack."""
        if not self.player: return

        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if giver:
            self.world.add_npc(giver)
            
            self.world.item_templates["token"] = {"type": "Item", "name": "Token", "stackable": True}
            
            q_id = "fetch_tokens"
            
            # Create proper Saga structure with top-level objective pointer for consistency
            objective_data = {"type": "fetch", "item_id": "token", "required_quantity": 5}
            
            self.player.runtime_state.quests.active[q_id] = {
                "instance_id": q_id, "type": "fetch", "state": "active",
                "giver_instance_id": giver.obj_id, "current_stage_index": 0,
                "rewards": {"xp": 100},
                # Pointer to active objective
                "objective": objective_data,
                "stages": [{
                    "stage_index": 0, "turn_in_id": giver.obj_id,
                    "objective": objective_data,
                    "completion_dialogue": "Thanks for the tokens!"
                }]
            }
            
            token = ItemFactory.create_item_from_template("token", self.world)
            if token:
                self.player.inventory.add_item(token, 10)
                
                from engine.commands.interaction.npcs import _handle_quest_dialogue
                msg = _handle_quest_dialogue(self.player, giver, self.world)
                
                self.assertIn("Complete", msg)
                self.assertEqual(self.player.inventory.count_item("token"), 5)

    def test_quest_multi_kill_update(self):
        """Verify killing one monster updates multiple active quests."""
        if not self.player: return
        
        def make_q(qid):
            obj = {"type": "kill", "target_template_id": "goblin", "required_quantity": 5, "current_quantity": 0}
            return {
                "instance_id": qid, "type": "kill", "state": "active", "current_stage_index": 0,
                "objective": obj, # Sync top-level
                "stages": [{"stage_index": 0, "objective": obj}]
            }
        
        self.player.runtime_state.quests.active["q1"] = make_q("q1")
        self.player.runtime_state.quests.active["q2"] = make_q("q2")
        
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": goblin})
            
            q1 = self.player.runtime_state.quests.active["q1"]["stages"][0]["objective"]
            q2 = self.player.runtime_state.quests.active["q2"]["stages"][0]["objective"]
            
            self.assertEqual(q1["current_quantity"], 1)
            self.assertEqual(q2["current_quantity"], 1)

    def test_reward_inventory_full(self):
        """Verify handling of rewards when inventory is full."""
        if not self.player: return
        
        q_id = "reward_full"
        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world, instance_id="giver")
        
        if giver:
             self.world.add_npc(giver)
             
             obj = {"type": "talk"}
             
             self.player.runtime_state.quests.active[q_id] = {
                "instance_id": q_id, "state": "active", "type": "talk", "current_stage_index": 0,
                "rewards": {"items": [{"item_id": "reward_item", "quantity": 1}]},
                "giver_instance_id": giver.obj_id,
                "objective": obj, # Sync top-level
                "stages": [{
                    "stage_index": 0, "turn_in_id": giver.obj_id,
                    "objective": obj,
                    "completion_dialogue": "Done."
                }]
            }
            
             self.player.inventory.max_slots = 1
             self.player.inventory.slots = [self.player.inventory.slots[0]]
             dummy = ItemFactory.create_item_from_template("item_iron_sword", self.world)
             if dummy: self.player.inventory.add_item(dummy)
             
             self.world.item_templates["reward_item"] = {"type": "Item", "name": "Reward"}
             
             from engine.commands.interaction.npcs import _handle_quest_dialogue
             msg = _handle_quest_dialogue(self.player, giver, self.world)
             
             self.assertIn("Complete", msg)
             # Item lost due to full inventory, but quest completes (as per current design decision for simplicity)
             self.assertEqual(self.player.inventory.count_item("reward_item"), 0)
