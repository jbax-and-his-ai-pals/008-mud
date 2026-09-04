# tests/singles/test_environment.py
from tests.fixtures import GameTestBase

class TestEnvironment(GameTestBase):

    def test_time_flow(self):
        """Verify game time advances and periods change."""
        tm = self.game.time_manager
        
        # 1. Force time to Noon (Day)
        tm.initialize_time(12 * 3600.0)
        self.assertEqual(tm.current_time_period, "afternoon") 
        
        # 2. Advance time by 7 hours (to 19:00 -> Dusk)
        # Update calculates delta based on real-time seconds config
        # We simulate passing enough real seconds to equal 7 game hours
        from engine.config import TIME_REAL_SECONDS_PER_GAME_DAY
        game_seconds_needed = 7 * 3600
        real_seconds_needed = game_seconds_needed / (86400 / TIME_REAL_SECONDS_PER_GAME_DAY)
        
        tm.update(real_seconds_needed + 1.0) # Add buffer
        
        # Check hour
        self.assertGreaterEqual(tm.hour, 19)
        self.assertEqual(tm.current_time_period, "dusk")

    def test_weather_command(self):
        """Verify weather system and command output."""
        wm = self.game.weather_manager
        
        # Explicitly set values
        wm.current_weather = "storm"
        wm.current_intensity = "severe"
        
        # Force player outdoors to ensure they can see the weather
        if self.player.current_region_id:
            region = self.world.get_region(self.player.current_region_id)
            if region:
                # Force outdoor property on current region for test reliability
                region.update_property("outdoors", True)
                if self.player.current_room_id:
                    room = region.get_room(self.player.current_room_id)
                    if room: room.update_property("outdoors", True)

        # Act
        result = self.game.process_command("weather")
        
        # Assert
        self.assertIsNotNone(result)
        
        # Explicit check for type checker
        if result:
            self.assertIn("storm", result.lower())
            self.assertIn("severe", result.lower())