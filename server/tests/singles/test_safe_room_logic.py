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
    def test_a_room_can_depart_from_its_regions_safety(self):
        """`is_location_safe` took a room id and ignored it, so a room authored
        `"safe_zone": false` in a safe region (night_shift's back alley,
        orbital_salvage's hold) stayed safe and its hostiles never attacked."""
        town = self.world.get_region("town")
        town.update_property("safe_zone", True)
        alley = Room("Alley", "Dark.", {"west": "town_square"}, obj_id="alley")
        alley.update_property("safe_zone", False)
        town.add_room("alley", alley)
        self.assertTrue(self.world.is_location_safe("town", "town_square"))
        self.assertFalse(self.world.is_location_safe("town", "alley"))
        self.assertTrue(self.world.is_location_safe("town"), "without a room the region decides")

    def test_a_safe_room_in_a_dangerous_region_is_found(self):
        wilds = Region("Wilds", "Rough.", obj_id="wilds")
        camp = Room("Camp", "A warded camp.", {}, obj_id="camp")
        camp.update_property("safe_zone", True)
        start = Room("Trail", "Open ground.", {"north": "camp"}, obj_id="trail")
        wilds.add_room("camp", camp)
        wilds.add_room("trail", start)
        self.world.add_region("wilds", wilds)
        self.world.get_region("town").update_property("safe_zone", False)
        self.assertEqual(("wilds", "camp"), self.world.find_nearest_safe_room("wilds", "trail"))

    def test_the_shipped_unsafe_rooms_are_unsafe(self):
        from engine.server.headless_server import HeadlessServer
        from pathlib import Path
        root = Path(__file__).resolve().parents[3] / "content_sets"
        for content_set, region_id, room_id in (
            ("night_shift", "depot", "back_alley"), ("night_shift", "depot", "alley_end"),
            ("orbital_salvage", "station", "hold"),
        ):
            server = HeadlessServer(db_path=":memory:", content_set_path=str(root / content_set))
            self.assertTrue(server.world.is_location_safe(region_id), content_set)
            self.assertFalse(server.world.is_location_safe(region_id, room_id), (content_set, room_id))
