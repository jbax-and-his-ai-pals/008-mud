# tests/batch/test_batch_quest_lifecycle_rewrite.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room

class TestBatchQuestLifecycleRewrite(GameTestBase):
    """
    Refactored test for Instance Quest Lifecycle.
    Manually constructs state to verify 'Clear Region' logic deterministically.
    """
    
    def test_clear_region_mechanics_isolated(self):
        """
        Verify that a quest tracking a specific region updates to 'ready_to_complete'
        only when all target mobs in that region are dead.
        """
        # --- 1. SETUP WORLD ---
        # Create a dedicated instance region
        instance_id = "inst_test_01"
        region = Region("Test Instance", "A test area.", obj_id=instance_id)
        room = Room("Boss Room", "Scary.", obj_id="boss_room")
        region.add_room("boss_room", room)
        self.world.add_region(instance_id, region)
        
        # Define target template
        target_tid = "test_boss_mob"
        self.world.npc_templates[target_tid] = {
            "name": "Test Boss", "faction": "hostile", "level": 5, "health": 50
        }
        
        # Spawn the target in the instance
        boss = NPCFactory.create_npc_from_template(target_tid, self.world)
        self.assertIsNotNone(boss, "Failed to create boss npc")
        if boss:
            boss.current_region_id = instance_id
            boss.current_room_id = "boss_room"
            self.world.add_npc(boss)
            
        # Spawn a decoy in a DIFFERENT region (should not count)
        decoy = NPCFactory.create_npc_from_template(target_tid, self.world)
        if decoy:
            decoy.current_region_id = "town"
            decoy.current_room_id = "town_square"
            self.world.add_npc(decoy)

        # --- 2. SETUP QUEST ---
        quest_id = "quest_clear_01"
        
        # Construct quest matching the schema expected by QuestManager.check_quest_completion
        quest_data = {
            "instance_id": quest_id,
            "title": "Clear the Test Instance",
            "type": "instance",
            "state": "active",
            "giver_instance_id": "quest_board",
            "instance_region_id": instance_id, # Crucial: Links quest to the specific region
            "completion_check_enabled": True,  # Crucial: Allows the check to run
            "current_stage_index": 0,
            "stages": [
                {
                    "stage_index": 0,
                    "description": "Defeat the boss.",
                    "objective": {
                        "type": "clear_region",
                        "target_template_id": target_tid
                    }
                }
            ]
        }
        
        self.player.runtime_state.quests.active[quest_id] = quest_data
        
        # --- 3. VERIFY ACTIVE STATE ---
        # Boss is alive in the region
        self.world.quest_manager.check_quest_completion()
        self.assertEqual(quest_data["state"], "active", "Quest should remain active while boss is alive.")
        
        # --- 4. KILL BOSS ---
        if boss:
            boss.health = 0
            boss.is_alive = False
            
        # Run Check
        self.world.quest_manager.check_quest_completion()
        
        # --- 5. VERIFY COMPLETION ---
        # The decoy in 'town' is still alive, but because the quest is scoped to 'instance_id',
        # it should ignore the decoy and mark complete.
        self.assertEqual(quest_data["state"], "ready_to_complete", "Quest should complete when instance targets are dead.")
        
        # --- 6. CLEANUP (Simulate Turn-in) ---
        # Move to completed
        self.player.runtime_state.quests.active.pop(quest_id)
        self.player.runtime_state.quests.completed[quest_id] = quest_data
        
        # Add entry point data needed for cleanup_quest_region to work (even if dummy)
        quest_data["entry_point"] = {
            "region_id": "town", "room_id": "town_square", "exit_command": "portal_temp"
        }
        
        # Run Cleanup
        self.world.cleanup_quest_region(quest_id)
        
        # Verify region removal
        self.assertNotIn(instance_id, self.world.regions, "Instance region should be removed after cleanup.")
        # Verify NPC removal
        if boss:
            self.assertNotIn(boss.obj_id, self.world.npcs, "Instance NPCs should be removed.")
        # Verify Decoy remains
        if decoy:
            self.assertIn(decoy.obj_id, self.world.npcs, "NPCs outside the instance should remain.")
