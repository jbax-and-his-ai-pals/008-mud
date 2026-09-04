# tests/singles/test_movement_directions.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestMovementDirections(GameTestBase):

    def test_vertical_movement(self):
        """Verify 'up' and 'down' work."""
        region = self.world.get_region("town")
        if region:
            ground = Room("Ground", "Low", {"up": "sky"}, obj_id="ground")
            sky = Room("Sky", "High", {"down": "ground"}, obj_id="sky")
            region.add_room("ground", ground)
            region.add_room("sky", sky)
            
            # FIX: Sync both player AND world location
            self.player.current_region_id = "town"
            self.player.current_room_id = "ground"
            self.world.current_region_id = "town"
            self.world.current_room_id = "ground"
            
            # Go Up
            self.world.change_room("up")
            self.assertEqual(self.player.current_room_id, "sky")
            
            # Go Down
            self.world.change_room("down")
            self.assertEqual(self.player.current_room_id, "ground")

    def test_custom_exit_names(self):
        """Verify non-standard exits (e.g. 'enter', 'portal') work."""
        region = self.world.get_region("town")
        if region:
            outside = Room("Outside", "Out", {"enter": "inside"}, obj_id="outside")
            inside = Room("Inside", "In", {"out": "outside"}, obj_id="inside")
            region.add_room("outside", outside)
            region.add_room("inside", inside)
            
            # FIX: Sync both player AND world location
            self.player.current_region_id = "town"
            self.player.current_room_id = "outside"
            self.world.current_region_id = "town"
            self.world.current_room_id = "outside"
            
            # "enter" is a valid exit key here
            self.world.change_room("enter")
            self.assertEqual(self.player.current_room_id, "inside")