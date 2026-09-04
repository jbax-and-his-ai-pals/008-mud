# tests/singles/test_environmental_vision.py
from tests.fixtures import GameTestBase
from engine.world.room import Room

class TestEnvironmentalVision(GameTestBase):

    def test_dark_room_description(self):
        """Verify room description acknowledges darkness."""
        room = self.world.get_current_room()
        if room:
            room.properties["dark"] = True
            
            # The 'look' command result
            result = self.game.process_command("look")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("very dark", result.lower())

    def test_noisy_room_description(self):
        """Verify room description acknowledges noise."""
        room = self.world.get_current_room()
        if room:
            room.properties["noisy"] = True
            
            result = self.game.process_command("look")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("filled with noise", result.lower())