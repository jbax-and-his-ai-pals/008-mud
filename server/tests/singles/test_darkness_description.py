# tests/singles/test_darkness_description.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestDarknessDescription(GameTestBase):

    def test_dark_room_feedback(self):
        """Verify 'It is very dark here' appears in descriptions of dark rooms."""
        # 1. Setup
        region = self.world.get_region("town")
        if not region: return
        
        dark_room = Room("Cellar", "A spooky cellar.", obj_id="dark_room")
        dark_room.properties["dark"] = True
        region.add_room("dark_room", dark_room)
        
        # 2. Move Player
        self.player.current_region_id = "town"
        self.player.current_room_id = "dark_room"
        self.world.current_region_id = "town"
        self.world.current_room_id = "dark_room"
        
        # 3. Act
        desc = self.world.look()
        
        # 4. Assert
        self.assertIn("very dark", desc)