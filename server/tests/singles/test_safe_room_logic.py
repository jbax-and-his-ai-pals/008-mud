# tests/singles/test_safe_room_logic.py
from tests.fixtures import GameTestBase
from engine.world.region import Region
from engine.world.room import Room

class TestSafeRoomLogic(GameTestBase):

    def test_find_nearest_safe_room(self):
        """Verify world finds the closest safe room across region boundaries."""
        # 1. Setup Dangerous Region
        danger_zone = Region("Danger", "Heck", obj_id="danger")
        danger_room = Room("Start", "Scary", {"south": "town:town_square"}, obj_id="danger_start")
        danger_zone.add_room("danger_start", danger_room)
        self.world.add_region("danger", danger_zone)
        
        # 2. Ensure Town is Safe
        town = self.world.get_region("town")
        if town:
            town.update_property("safe_zone", True)
            
            # 3. Connect Danger -> Town Square
            # (Handled by the exit string in Room definition above)
            
            # 4. Act: Find nearest safe room from the danger room
            result = self.world.find_nearest_safe_room("danger", "danger_start")
            
            # 5. Assert: Should return Town Square (since it is adjacent and safe)
            self.assertIsNotNone(result)
            if result:
                self.assertEqual(result[0], "town")
                self.assertEqual(result[1], "town_square")