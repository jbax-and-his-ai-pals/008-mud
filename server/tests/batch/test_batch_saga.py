# tests/batch/test_batch_saga.py
import time
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestBatchSaga(GameTestBase):

    def test_saga_flow(self):
        """Verify multi-stage saga progression."""
        qm = self.world.quest_manager
        
        # Inject Data
        self.world.item_templates["item_bloody_tabard"] = {"type": "Item", "name": "Tabard", "properties": {"quest_item": True}}
        self.world.npc_templates["town_guard"] = {"name": "Guard", "faction": "friendly"}
        self.world.npc_templates["wandering_mage"] = {"name": "Mage", "faction": "friendly"}
        self.world.npc_templates["river_troll"] = {"name": "Troll", "faction": "hostile"}

        saga_id = "saga_missing_guard"
        target_delivery_id = "specific_tabard_instance_id"
        
        # USE NEW ATTRIBUTE NAME: quest_templates
        qm.quest_templates[saga_id] = {
            "title": "The Missing Guard",
            "type": "saga",
            "rewards": {"xp": 500},
            "stages": [
                {
                    "stage_index": 0, "description": "Fetch.",
                    "objective": {"type": "fetch", "item_id": "item_bloody_tabard", "required_quantity": 1},
                    "turn_in_id": "guard_captain"
                },
                {
                    "stage_index": 1, "description": "Deliver.",
                    "objective": {
                        "type": "deliver", 
                        "item_instance_id": target_delivery_id, 
                        "item_to_deliver_name": "Bloody Tabard",
                        "recipient_instance_id": "alchemist"
                    },
                    "turn_in_id": "alchemist"
                },
                {
                    "stage_index": 2, "description": "Kill.",
                    "objective": {"type": "kill", "target_template_id": "river_troll", "required_quantity": 1, "current_quantity": 0},
                    "turn_in_id": "guard_captain"
                }
            ]
        }
        
        # USE NEW METHOD: start_quest
        success = qm.start_quest(saga_id, self.player)
        self.assertTrue(success, "Failed to start saga")
        
        inst_id = list(self.player.runtime_state.quests.active.keys())[0]
        quest = self.player.runtime_state.quests.active[inst_id]
        
        # Create NPCs
        captain = NPCFactory.create_npc_from_template("town_guard", self.world, instance_id="guard_captain", name="Captain")
        alchemist = NPCFactory.create_npc_from_template("wandering_mage", self.world, instance_id="alchemist", name="Alchemist")
        
        if captain and alchemist:
            captain.current_region_id = self.player.current_region_id
            captain.current_room_id = self.player.current_room_id
            alchemist.current_region_id = self.player.current_region_id
            alchemist.current_room_id = self.player.current_room_id
            self.world.add_npc(captain)
            self.world.add_npc(alchemist)
            
            # --- Stage 0 ---
            tabard = ItemFactory.create_item_from_template("item_bloody_tabard", self.world)
            if tabard: self.player.inventory.add_item(tabard)
            
            # Turn In
            res = self.game.process_command(f"talk {captain.name} complete")
            if res: self.assertIn("Objective Complete", res)
            self.assertEqual(quest["current_stage_index"], 1)
            
            # --- Stage 1 ---
            tabard_2 = ItemFactory.create_item_from_template("item_bloody_tabard", self.world)
            if tabard_2:
                tabard_2.obj_id = target_delivery_id
                self.player.inventory.add_item(tabard_2)
            
            res_2 = self.game.process_command(f"talk {alchemist.name} complete")
            if res_2: self.assertIn("Objective Complete", res_2)
            self.assertEqual(quest["current_stage_index"], 2)
            
            # --- Stage 2 ---
            troll = NPCFactory.create_npc_from_template("river_troll", self.world)
            if troll:
                self.world.dispatch_event("npc_killed", {"player": self.player, "npc": troll})
                self.assertEqual(quest["state"], "ready_to_complete")
                
                res_3 = self.game.process_command(f"talk {captain.name} complete")
                if res_3: self.assertIn("Quest Complete", res_3)
                
                self.assertNotIn(inst_id, self.player.runtime_state.quests.active)
                self.assertIn(inst_id, self.player.runtime_state.quests.completed)
