# tests/singles/test_dynamic_region_exit_linkage.py
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator
from engine.world.room import Room

class TestDynamicRegionExitLinkage(GameTestBase):

    def test_portal_back_link(self):
        """Verify the 'portal' in a generated dungeon leads back to the spawn point."""
        # 1. Setup Start Room
        start_region_id = "town"
        start_room_id = "town_square"
        
        self.player.current_region_id = start_region_id
        self.player.current_room_id = start_room_id
        self.world.current_region_id = start_region_id
        self.world.current_room_id = start_room_id

        # 2. Generate Region via Command (simulated logic)
        gen = RegionGenerator(self.world)
        result = gen.generate_region("caves", 3)
        self.assertIsNotNone(result)
        
        if result:
            new_region, entry_id = result
            self.world.add_region(new_region.obj_id, new_region)
            
            # Manual Linkage (mimicking genregion_handler)
            current_room = self.world.get_current_room()
            if current_room:
                current_room.exits["portal"] = f"{new_region.obj_id}:{entry_id}"
                
                entry_room = new_region.get_room(entry_id)
                if entry_room:
                    entry_room.exits["portal"] = f"{start_region_id}:{start_room_id}"
            
            # 3. Test Entry
            self.world.change_room("portal")
            self.assertEqual(self.player.current_region_id, new_region.obj_id)
            
            # 4. Test Exit
            self.world.change_room("portal")
            self.assertEqual(self.player.current_region_id, start_region_id)
            self.assertEqual(self.player.current_room_id, start_room_id)