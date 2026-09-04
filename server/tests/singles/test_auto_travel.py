# tests/singles/test_auto_travel.py
from typing import cast, List
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room
from engine.world.region import Region

class TestAutoTravel(GameTestBase):
    
    def setUp(self):
        super().setUp()
        # Setup a dedicated test region to avoid conflicts with pre-existing 'town' data
        test_region = Region("Travel Zone", "A testing area", obj_id="travel_zone")
        
        # Linear path: Room A -> Room B -> Room C
        room_a = Room("Room A", "Start", {"north": "room_b"}, obj_id="room_a")
        room_b = Room("Room B", "Middle", {"north": "room_c", "south": "room_a"}, obj_id="room_b")
        room_c = Room("Room C", "End", {"south": "room_b"}, obj_id="room_c")
        
        test_region.add_room("room_a", room_a)
        test_region.add_room("room_b", room_b)
        test_region.add_room("room_c", room_c)
        
        self.world.add_region("travel_zone", test_region)
        
        # Place player
        self.world.current_region_id = "travel_zone"
        self.world.current_room_id = "room_a"
        if self.player:
            self.player.current_region_id = "travel_zone"
            self.player.current_room_id = "room_a"

        # Create Guide
        if "test_villager" not in self.world.npc_templates:
            self.world.npc_templates["test_villager"] = {
                "name": "Villager", "description": "Normal.", "faction": "neutral"
            }
        
        self.guide = NPCFactory.create_npc_from_template("test_villager", self.world)
        if self.guide:
            self.guide.name = "Guide"
            self.guide.current_region_id = "travel_zone"
            self.guide.current_room_id = "room_a"
            self.world.add_npc(self.guide)

    def test_auto_travel_sequence(self):
        """Verify guide leads player through rooms step-by-step."""
        if not self.guide or not self.player:
            self.fail("Setup failed: Guide or Player is None")
            return
        
        # 1. Start Travel
        path: List[str] = ["north", "north"] # A -> B, then B -> C
        self.game.start_auto_travel(path, self.guide)
        self.assertTrue(self.game.is_auto_traveling)
        
        # 2. Step 1 (A -> B)
        self.game.auto_travel_timer = 0 
        self.game._update_auto_travel()
        self.assertEqual(self.player.current_room_id, "room_b")
        
        # 3. Step 2 (B -> C)
        self.game.auto_travel_timer = 0
        self.game._update_auto_travel()
        self.assertEqual(self.player.current_room_id, "room_c")
        
        # 4. Finalization Call
        # The path is now empty. The next call triggers arrival logic and stops travel.
        self.game.auto_travel_timer = 0
        self.game._update_auto_travel()
        
        self.assertFalse(self.game.is_auto_traveling, "Travel should end after path is exhausted.")

    def test_auto_travel_interruption(self):
        """Verify travel stops if the guide dies."""
        if not self.guide:
            return
        
        self.game.start_auto_travel(["north"], self.guide)
        self.guide.is_alive = False
        
        self.game.auto_travel_timer = 0
        self.game._update_auto_travel()
        
        self.assertFalse(self.game.is_auto_traveling, "Auto-travel should stop if guide is not alive.")