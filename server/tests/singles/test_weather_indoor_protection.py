# tests/singles/test_weather_indoor_protection.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestWeatherIndoorProtection(GameTestBase):

    def test_indoor_description_filtering(self):
        """Verify weather descriptions are hidden when indoors."""
        # 1. Setup Weather
        self.game.weather_manager.current_weather = "storm"
        
        # 2. Setup Indoor Room
        region = self.world.get_region("town")
        if not region: return
        
        room = Room("Inn", "Cozy.", obj_id="inn_room")
        room.properties["outdoors"] = False
        region.add_room("inn_room", room)
        
        self.player.current_region_id = "town"
        self.player.current_room_id = "inn_room"
        self.world.current_region_id = "town"
        self.world.current_room_id = "inn_room"
        
        # 3. Act
        desc = self.world.look()
        
        # 4. Assert
        self.assertNotIn("storm", desc)
        
    def test_outdoor_description_shows(self):
        """Verify weather shows outdoors."""
        self.game.weather_manager.current_weather = "storm"
        
        region = self.world.get_region("town")
        if not region: return
        
        room = Room("Garden", "Open.", obj_id="garden_room")
        room.properties["outdoors"] = True
        region.add_room("garden_room", room)
        
        self.player.current_region_id = "town"
        self.player.current_room_id = "garden_room"
        self.world.current_region_id = "town"
        self.world.current_room_id = "garden_room"
        
        desc = self.world.look()
        
        self.assertIn("storm", desc)