# engine/core/time_manager.py
"""
Core system for managing in-game time, date, and seasons.
Refactored to use Delta Time (dt) for stable simulation.
"""
import time
from typing import Dict, Any, Optional, Tuple

from engine.config import (TIME_DAWN_HOUR, TIME_DAY_NAMES,
                         TIME_DAYS_PER_MONTH, TIME_DUSK_HOUR,
                         TIME_MONTH_NAMES,
                         TIME_MONTHS_PER_YEAR, TIME_NIGHT_HOUR,
                         TIME_REAL_SECONDS_PER_GAME_DAY, TIME_UPDATE_THRESHOLD)
from engine.config.config_game import TIME_AFTERNOON_HOUR, TIME_MORNING_HOUR


class TimeManager:
    def __init__(self):
        self.game_time: float = 0.0
        self.hour: int = 12
        self.minute: int = 0
        self.day: int = 1
        self.month: int = 1
        self.year: int = 1
        self.current_time_period: str = "day"
        self.time_data: Dict[str, Any] = {}
        self.initialize_time()

    def initialize_time(self, game_time: float = 0.0):
        """Resets or initializes the time state."""
        self.game_time = game_time
        self._recalculate_date_from_game_time()
        self._update_time_period()
        self._update_time_data_for_ui()

    def update(self, dt: float) -> Optional[Tuple[str, str]]:
        """
        Updates the game time based on the delta time (dt) from the game loop.
        dt: Time in seconds since the last frame.
        Returns old and new time periods if a change occurred.
        """
        seconds_per_day = TIME_REAL_SECONDS_PER_GAME_DAY
        if seconds_per_day <= 0: return None

        # Calculate how many game-seconds pass per real-second
        game_seconds_per_real_second = 86400 / seconds_per_day

        # Advance game time
        elapsed_game_time = dt * game_seconds_per_real_second
        old_game_time = self.game_time
        self.game_time += elapsed_game_time
        
        # Only recalculate calendar if enough time has passed (Optimization)
        if abs(self.game_time - old_game_time) > TIME_UPDATE_THRESHOLD:
            old_period = self.current_time_period
            self._recalculate_date_from_game_time()
            self._update_time_period()
            self._update_time_data_for_ui()

            if self.current_time_period != old_period:
                return (old_period, self.current_time_period)
        return None

    def _recalculate_date_from_game_time(self):
        total_seconds = int(self.game_time)
        self.minute = (total_seconds // 60) % 60
        self.hour = (total_seconds // 3600) % 24
        total_days = total_seconds // 86400
        self.year = 1 + (total_days // (TIME_DAYS_PER_MONTH * TIME_MONTHS_PER_YEAR))
        days_this_year = total_days % (TIME_DAYS_PER_MONTH * TIME_MONTHS_PER_YEAR)
        self.month = 1 + (days_this_year // TIME_DAYS_PER_MONTH)
        self.day = 1 + (days_this_year % TIME_DAYS_PER_MONTH)

    def _update_time_period(self):
        if self.hour >= TIME_NIGHT_HOUR or self.hour < TIME_DAWN_HOUR:
            self.current_time_period = "night"
        elif self.hour < TIME_MORNING_HOUR:
            self.current_time_period = "dawn"
        elif self.hour < TIME_AFTERNOON_HOUR:
            self.current_time_period = "morning"
        elif self.hour < TIME_DUSK_HOUR:
            self.current_time_period = "afternoon"
        else: # self.hour < TIME_NIGHT_HOUR
            self.current_time_period = "dusk"

    def _update_time_data_for_ui(self):
        day_name = TIME_DAY_NAMES[(self.day - 1) % len(TIME_DAY_NAMES)]
        month_name = TIME_MONTH_NAMES[(self.month - 1) % len(TIME_MONTH_NAMES)]
        seasons = ["winter", "spring", "summer", "fall"]
        season_idx = (self.month - 1) * len(seasons) // TIME_MONTHS_PER_YEAR
        self.time_data = {
            "hour": self.hour, "minute": self.minute, "day": self.day, "month": self.month, "year": self.year,
            "day_name": day_name, "month_name": month_name, "season": seasons[season_idx],
            "time_period": self.current_time_period, "time_str": f"{self.hour:02d}:{self.minute:02d}",
            "date_str": f"{day_name}, {self.day} {month_name}, Year {self.year}"
        }

    def get_time_transition_message(self, old_period: str, new_period: str) -> str:
        transitions = {
            "night-dawn": "Dawn breaks, casting long shadows.",
            "dawn-morning": "The sun climbs higher into the morning sky.",
            "afternoon-dusk": "The afternoon sun begins its descent, painting the sky in warm colors.",
            "dusk-night": "The last light fades from the sky. Night has fallen."
        }
        return transitions.get(f"{old_period}-{new_period}", "")

    def get_time_state_for_save(self) -> Dict[str, Any]:
         return {"game_time": self.game_time}

    def apply_loaded_time_state(self, time_state: Optional[Dict[str, Any]]):
        if time_state and isinstance(time_state, dict):
             self.initialize_time(time_state.get("game_time", 0.0))
        else:
             self.initialize_time()