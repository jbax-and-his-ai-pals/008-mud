# tests/singles/test_command_teleport.py
from tests.fixtures import GameTestBase

class TestCommandTeleport(GameTestBase):

    def test_teleport_valid(self):
        """Verify teleport moves player to valid coordinates."""
        # 1. Setup destination
        dest_region = "town"
        dest_room = "town_square"
        
        # Ensure we aren't already there
        self.player.current_room_id = "somewhere_else"
        self.world.current_room_id = "somewhere_else"

        # 2. Act
        result = self.game.process_command(f"teleport {dest_region} {dest_room}")
        
        # 3. Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Teleported to", result)
            self.assertEqual(self.player.current_region_id, dest_region)
            self.assertEqual(self.player.current_room_id, dest_room)
            self.assertEqual(self.world.current_region_id, dest_region)

    def test_teleport_invalid(self):
        """Verify teleport handles bad IDs gracefully."""
        start_room = self.player.current_room_id
        
        result = self.game.process_command("teleport fake_region fake_room")
        
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Could not find", result)
            self.assertEqual(self.player.current_room_id, start_room)