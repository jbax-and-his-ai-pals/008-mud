# tests/singles/test_npc_cross_region_pathing.py
from tests.fixtures import GameTestBase
from engine.world.region import Region
from engine.world.room import Room

class TestNPCCrossRegionPathing(GameTestBase):

    def test_find_path_across_regions(self):
        """Verify A* correctly bridges different regions via their exits."""
        # Setup Region A
        reg_a = Region("A", "A", obj_id="reg_a")
        room_a1 = Room("A1", "", {"east": "reg_b:b1"}, obj_id="a1")
        reg_a.add_room("a1", room_a1)
        self.world.add_region("reg_a", reg_a)
        
        # Setup Region B
        reg_b = Region("B", "B", obj_id="reg_b")
        room_b1 = Room("B1", "", {"west": "reg_a:a1", "north": "b2"}, obj_id="b1")
        room_b2 = Room("B2", "", {"south": "b1"}, obj_id="b2")
        reg_b.add_room("b1", room_b1)
        reg_b.add_room("b2", room_b2)
        self.world.add_region("reg_b", reg_b)
        
        # Act: Path from A1 to B2
        # Expected: East (to B1) -> North (to B2)
        path = self.world.find_path("reg_a", "a1", "reg_b", "b2")
        
        # Assert
        self.assertIsNotNone(path)
        if path:
            self.assertEqual(path, ["east", "north"])