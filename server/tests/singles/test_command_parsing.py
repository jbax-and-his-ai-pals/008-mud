# tests/singles/test_command_parsing.py
from tests.fixtures import GameTestBase

class TestCommandParsing(GameTestBase):
    
    def test_aliases(self):
        """Verify command aliases work (e.g., 'i' for 'inventory')."""
        # "i" -> inventory
        result_i = self.game.process_command("i")
        self.assertIsNotNone(result_i)
        if result_i:
            self.assertIn("INVENTORY", result_i)
        
        # "l" -> look
        result_l = self.game.process_command("l")
        self.assertIsNotNone(result_l)
        
        # Safe access to region ID
        region_id = self.player.current_region_id
        if result_l and region_id:
            self.assertIn(region_id.upper(), result_l) # Room title
        
        # Movement: "n" -> north
        # Setup room with north exit
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square" # Has north exit
        
        # Store location
        start_room = self.player.current_room_id
        
        # Act
        self.game.process_command("n")
        
        # Assert moved
        self.assertNotEqual(self.player.current_room_id, start_room)

    def test_case_insensitivity(self):
        """Verify commands work regardless of case."""
        # Mixed case command
        result = self.game.process_command("InVeNtOrY")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("INVENTORY", result)
        
        # Mixed case args
        # "look Town Square"
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        result = self.game.process_command("LoOk")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("TOWN SQUARE", result)

    def test_unknown_command(self):
        """Verify feedback for invalid commands."""
        result = self.game.process_command("xyzzy")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Unknown command", result)