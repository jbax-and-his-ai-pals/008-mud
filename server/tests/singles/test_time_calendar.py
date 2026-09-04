# tests/singles/test_time_calendar.py
from tests.fixtures import GameTestBase
from engine.config import TIME_DAYS_PER_MONTH

class TestTimeCalendar(GameTestBase):

    def test_day_rollover(self):
        """Verify advancing time past 24 hours increments day."""
        tm = self.game.time_manager
        tm.initialize_time(0.0) # Day 1
        
        # Advance 25 hours (25 * 3600 seconds)
        # Note: update takes seconds
        seconds_to_advance = 25 * 3600
        
        # Simulate real-time passing that results in game-time passing
        # We can directly manipulate game_time for testing precision logic
        tm.game_time += seconds_to_advance
        tm._recalculate_date_from_game_time()
        
        self.assertEqual(tm.day, 2)
        self.assertEqual(tm.hour, 1)

    def test_month_end_rollover(self):
        """Verify day rolls over to 1 and month increments after full month."""
        tm = self.game.time_manager
        tm.initialize_time(0.0)
        
        # Advance exactly one month
        seconds_in_month = TIME_DAYS_PER_MONTH * 24 * 3600
        
        tm.game_time += seconds_in_month
        tm._recalculate_date_from_game_time()
        
        self.assertEqual(tm.month, 2)
        self.assertEqual(tm.day, 1)