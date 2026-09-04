# tests/singles/test_npc_schedules.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room
from engine.world.region import Region

class TestNPCSchedules(GameTestBase):
    
    def setUp(self):
        super().setUp()
        
        # Setup a dummy region with two specific rooms
        self.region = Region("Schedule Town", "Testing", obj_id="schedule_town")
        self.room_home = Room("Home", "Bedroom", obj_id="room_home")
        self.room_work = Room("Work", "Office", obj_id="room_work")
        
        # Connect them so pathfinding works (required for perform_schedule to calculate path)
        self.room_home.exits["north"] = "room_work"
        self.room_work.exits["south"] = "room_home"
        
        self.region.add_room("room_home", self.room_home)
        self.region.add_room("room_work", self.room_work)
        self.world.add_region("schedule_town", self.region)
        
        # Create NPC
        self.npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not self.npc:
            # Fallback if template doesn't exist
            self.npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
            
        self.assertIsNotNone(self.npc, "Failed to create NPC")
        
        if self.npc:
            self.npc.current_region_id = "schedule_town"
            self.npc.current_room_id = "room_home"
            self.npc.behavior_type = "scheduled"
            self.world.add_npc(self.npc)
            
            # Define specific schedule
            # 08:00 -> Work
            # 18:00 -> Home
            self.npc.schedule = {
                "8": {"region_id": "schedule_town", "room_id": "room_work", "activity": "working"},
                "18": {"region_id": "schedule_town", "room_id": "room_home", "activity": "sleeping"}
            }

    def test_schedule_transition(self):
        """Verify NPC moves when time changes."""
        if not self.npc: return

        # 1. Set Time to 09:00 (Work Time)
        self.game.time_manager.hour = 9
        
        # Reset movement cooldown to ensure instant reaction
        self.npc.last_moved = 0
        
        # Update NPC (This triggers AI)
        self.npc.update(self.world, time.time())
        
        # Verify NPC moved (or started moving) towards work
        # Since it's 1 step away, it should arrive immediately if perform_schedule works
        self.assertEqual(self.npc.current_room_id, "room_work", "NPC should have moved to work.")
        self.assertEqual(self.npc.ai_state.get("current_activity"), "working")

        # 2. Set Time to 19:00 (Home Time)
        self.game.time_manager.hour = 19
        self.npc.last_moved = 0
        
        # Update NPC
        self.npc.update(self.world, time.time())
        
        # Verify NPC moved back home
        self.assertEqual(self.npc.current_room_id, "room_home", "NPC should have moved home.")
        self.assertEqual(self.npc.ai_state.get("current_activity"), "sleeping")