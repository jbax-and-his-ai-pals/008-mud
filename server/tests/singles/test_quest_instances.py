# tests/singles/test_quest_instances.py
from typing import cast, Dict, Any, Optional
from tests.fixtures import GameTestBase
from engine.world.instance_manager import InstanceManager
from engine.world.room import Room
from engine.world.region import Region

class TestQuestInstances(GameTestBase):
    
    def setUp(self):
        super().setUp()
        self.instance_manager = self.world.instance_manager
        
        # Ensure 'town' region exists for the test anchor
        if "town" not in self.world.regions:
            town = Region("Town", "A test town", obj_id="town")
            town.add_room("town_square", Room("Town Square", "Center", obj_id="town_square"))
            self.world.add_region("town", town)

        # Define a mock quest data structure
        self.quest_data: Dict[str, Any] = {
            "instance_id": "test_quest_01",
            "entry_point": {
                "region_id": "town",
                "room_id": "town_square",
                "exit_command": "enter_cellar"
            },
            "instance_region": {
                "region_name": "Test Cellar",
                "region_description": "A spooky cellar.",
                "rooms": {
                    "entry_hall": {
                        "name": "Entry Hall",
                        "description": "Dark.",
                        "exits": { "dynamic_exit": "dynamic_exit" }
                    }
                }
            },
            "objective": { "target_template_id": "giant_rat" },
            "layout_generation_config": { "target_count": [1, 1] }
        }

    def test_instantiation_and_cleanup(self):
        """Verify dynamic regions are created, linked, and destroyed."""
        # 1. Instantiate
        # Explicitly ensure player is set for Pylance/MyPy
        self.assertIsNotNone(self.world.player, "Player should be initialized in fixture.")
        
        success, msg, giver_id = self.instance_manager.instantiate_quest_region(self.quest_data)
        self.assertTrue(success, f"Instantiation failed: {msg}")
        
        generated_region_id = self.quest_data.get("instance_region_id")
        self.assertIsNotNone(generated_region_id, "Region ID was not generated in quest data.")
        
        # Type guard for Pylance
        if generated_region_id:
            # 2. Verify World State (Region exists)
            self.assertIn(generated_region_id, self.world.regions)
            
            # 3. Verify Linkage (Town Square has exit)
            town_region = self.world.get_region("town")
            self.assertIsNotNone(town_region, "Town region missing.")
            
            if town_region:
                town_square = town_region.get_room("town_square")
                self.assertIsNotNone(town_square, "Town square room missing.")
                
                if town_square:
                    self.assertIn("enter_cellar", town_square.exits)
                    exit_dest = town_square.exits.get("enter_cellar")
                    self.assertIsNotNone(exit_dest)
                    if exit_dest:
                        self.assertTrue(exit_dest.startswith(generated_region_id))
            
            # 4. Simulate Completion & Cleanup
            # Mock the quest being in completed log
            if self.player:
                self.player.runtime_state.quests.completed["test_quest_01"] = self.quest_data
            
            self.instance_manager.cleanup_quest_region("test_quest_01")
            
            # 5. Verify Cleanup
            self.assertNotIn(generated_region_id, self.world.regions, "Region should be deleted.")
            
            if town_region and town_square:
                self.assertNotIn("enter_cellar", town_square.exits, "Temporary exit should be removed.")
