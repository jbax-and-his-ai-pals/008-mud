# tests/singles/test_quest_reward_overflow.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestQuestRewardOverflow(GameTestBase):

    def test_delivery_reward_space_check(self):
        """Verify quest completion checks inventory space for rewards."""
        # 1. Setup Quest
        quest_id = "deliver_test"
        package_id = "package_1"
        objective_data = {
            "type": "deliver",
            "item_instance_id": package_id,
            "recipient_instance_id": "recipient_1",
            "item_to_deliver_name": "Package"
        }

        self.player.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id,
            "type": "deliver",
            "state": "active",
            "current_stage_index": 0,
            "giver_instance_id": "sender",
            "rewards": { "items": [{"item_id": "reward_sword", "quantity": 1}] },
            "objective": objective_data, # Sync top-level for give_handler logic
            "stages": [
                {
                    "stage_index": 0,
                    "turn_in_id": "recipient_1",
                    "objective": objective_data
                }
            ]
        }
        
        # 2. Add Package to inventory
        self.world.item_templates["pkg"] = {"type": "Item", "name": "Package", "weight": 1}
        pkg = ItemFactory.create_item_from_template("pkg", self.world)
        if pkg: 
            pkg.obj_id = package_id # Ensure ID matches objective
            self.player.inventory.add_item(pkg)
            
        # 3. Fill Inventory (Max slots)
        self.player.inventory.max_slots = 20
        self.world.item_templates["filler"] = {"type": "Item", "name": "Filler"}
        
        for i in range(19):
            it = ItemFactory.create_item_from_template("filler", self.world)
            if it: 
                it.obj_id = f"fill_{i}" # Unique to prevent stack
                self.player.inventory.add_item(it)
                
        self.assertEqual(self.player.inventory.get_empty_slots(), 0)
        
        # 4. Turn In Logic simulation
        # Create recipient with correct ID to match objective
        npc = NPCFactory.create_npc_from_template(
            "wandering_villager", 
            self.world, 
            instance_id="recipient_1", # Fixed ID
            name="Unique Recipient" 
        )
        self.assertIsNotNone(npc, "Failed to create recipient NPC.")
        
        if npc: 
            if self.player.current_region_id and self.player.current_room_id:
                npc.current_region_id = self.player.current_region_id
                npc.current_room_id = self.player.current_room_id
                self.world.add_npc(npc)
                
                # Act: Use the unique name
                result = self.game.process_command(f"give Package to Unique Recipient")
                
                # Assert Success (Slot was freed, then filled)
                self.assertIsNotNone(result)
                if result:
                    self.assertIn("Quest Complete", result)
                    self.assertNotIn("inventory is full", result)
            else:
                self.fail("Player location invalid.")
