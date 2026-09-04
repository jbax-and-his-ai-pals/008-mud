# tests/singles/test_time_descriptions.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestTimeDescriptions(GameTestBase):

    def test_description_changes_with_time(self):
        """Verify room description updates based on time period."""
        # 1. Setup Room with time-specific descriptions
        region = self.world.get_region("town")
        if not region: return
        
        room = Room("Clock Tower", "A tall tower.", obj_id="clock_tower")
        room.time_descriptions = {
            "day": "The sun shines on the clock face.",
            "night": "The clock face glows in the moonlight."
        }
        region.add_room("clock_tower", room)
        
        # Sync BOTH Player and World state
        self.player.current_region_id = "town"
        self.player.current_room_id = "clock_tower"
        self.world.current_region_id = "town"
        self.world.current_room_id = "clock_tower"
        
        # 2. Set Time to Day (12:00)
        self.game.time_manager.initialize_time(12 * 3600.0)
        desc_day = self.world.look()
        self.assertIn("sun shines", desc_day)
        self.assertNotIn("moonlight", desc_day)
        
        # 3. Set Time to Night (23:00)
        self.game.time_manager.initialize_time(23 * 3600.0)
        desc_night = self.world.look()
        self.assertIn("moonlight", desc_night)
        self.assertNotIn("sun shines", desc_night)