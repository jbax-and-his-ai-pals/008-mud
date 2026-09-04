# tests/singles/test_weather_visibility.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestWeatherVisibility(GameTestBase):

    def test_weather_context(self):
        """Verify weather is described only when outdoors."""
        # 1. Setup Weather
        self.game.weather_manager.current_weather = "storm"
        
        # 2. Setup Rooms
        region = self.world.get_region("town")
        if not region: return
        
        outdoor_room = Room("Garden", "Outside.", obj_id="out_room")
        outdoor_room.properties["outdoors"] = True
        
        indoor_room = Room("Cellar", "Inside.", obj_id="in_room")
        indoor_room.properties["outdoors"] = False
        
        region.add_room("out_room", outdoor_room)
        region.add_room("in_room", indoor_room)
        
        # 3. Check Outdoors
        # Update World state so world.look() finds the correct room
        self.world.current_region_id = "town"
        self.world.current_room_id = "out_room"
        self.player.current_region_id = "town"
        self.player.current_room_id = "out_room"
        
        desc_out = self.world.look()
        self.assertIn("weather is storm", desc_out)
        
        # 4. Check Indoors
        self.world.current_room_id = "in_room"
        self.player.current_room_id = "in_room"
        
        desc_in = self.world.look()
        self.assertNotIn("weather is storm", desc_in)