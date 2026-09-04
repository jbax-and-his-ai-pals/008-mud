# tests/singles/test_calendar_rollover.py
from tests.fixtures import GameTestBase
from engine.config import TIME_DAYS_PER_MONTH, TIME_MONTHS_PER_YEAR

class TestCalendarRollover(GameTestBase):

    def test_year_rollover(self):
        """Verify that passing enough time increments the year correctly."""
        tm = self.game.time_manager
        
        # 1. Start at Year 1, Month 1, Day 1
        tm.initialize_time(0.0)
        self.assertEqual(tm.year, 1)
        self.assertEqual(tm.month, 1)
        self.assertEqual(tm.day, 1)
        
        # 2. Calculate seconds for 1 full year
        # seconds = days_per_month * months_per_year * seconds_per_day (86400)
        total_days = TIME_DAYS_PER_MONTH * TIME_MONTHS_PER_YEAR
        seconds_for_year = float(total_days * 86400)
        
        # 3. Add nearly a year (Year 1, Month 12, Day 30)
        # We subtract a small amount to stay in Year 1
        tm.initialize_time(seconds_for_year - 100.0)
        self.assertEqual(tm.year, 1)
        self.assertEqual(tm.month, TIME_MONTHS_PER_YEAR)
        self.assertEqual(tm.day, TIME_DAYS_PER_MONTH)
        
        # 4. Roll over to Year 2
        tm.initialize_time(seconds_for_year + 100.0)
        self.assertEqual(tm.year, 2)
        self.assertEqual(tm.month, 1)
        self.assertEqual(tm.day, 1)

    def test_month_rollover(self):
        """Verify day-to-month rollover logic."""
        tm = self.game.time_manager
        tm.initialize_time(0.0)
        
        # Advance to last day of first month
        tm.initialize_time(float((TIME_DAYS_PER_MONTH - 1) * 86400))
        self.assertEqual(tm.day, TIME_DAYS_PER_MONTH)
        self.assertEqual(tm.month, 1)
        
        # Advance one more day
        tm.initialize_time(float(TIME_DAYS_PER_MONTH * 86400))
        self.assertEqual(tm.day, 1)
        self.assertEqual(tm.month, 2)