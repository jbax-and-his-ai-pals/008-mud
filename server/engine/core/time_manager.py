# engine/core/time_manager.py
"""
Core system for managing in-game time, date, and seasons.
Refactored to use Delta Time (dt) for stable simulation.
"""
import time
from typing import Any, Dict, List, Optional, Tuple

from engine.config import (TIME_DAWN_HOUR, DEFAULT_TIME_DAY_NAMES,
                         TIME_DAYS_PER_MONTH, TIME_DUSK_HOUR,
                         DEFAULT_TIME_MONTH_NAMES,
                         TIME_MONTHS_PER_YEAR, TIME_NIGHT_HOUR,
                         TIME_REAL_SECONDS_PER_GAME_DAY, TIME_UPDATE_THRESHOLD)
from engine.config.config_game import TIME_AFTERNOON_HOUR, TIME_MORNING_HOUR


def _resolve_calendar_names(world, key: str, default: List[str]) -> List[str]:
    if world is None:
        return default
    ruleset_section = getattr(world, "ruleset_section", None)
    if ruleset_section is None:
        return default
    names = ruleset_section("calendar").get(key)
    if isinstance(names, list) and names and all(isinstance(n, str) and n for n in names):
        return names
    return default



def _resolve_initial_game_time(world) -> float:
    """Read an optional content-defined initial clock, falling back to midnight."""
    if world is None or not hasattr(world, "ruleset_section"):
        return 0.0
    start_time = world.ruleset_section("calendar").get("start_time")
    if not isinstance(start_time, dict):
        return 0.0
    hour = start_time.get("hour", 0)
    minute = start_time.get("minute", 0)
    if isinstance(hour, bool) or isinstance(minute, bool):
        return 0.0
    if not isinstance(hour, int) or not isinstance(minute, int):
        return 0.0
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        return 0.0
    return float((hour * 3600) + (minute * 60))

class TimeManager:
    def __init__(self, world=None):
        self.day_names: List[str] = _resolve_calendar_names(world, "day_names", DEFAULT_TIME_DAY_NAMES)
        self.month_names: List[str] = _resolve_calendar_names(world, "month_names", DEFAULT_TIME_MONTH_NAMES)
        self.game_time: float = 0.0
        self.initial_game_time = _resolve_initial_game_time(world)
        self.hour: int = 12
        self.minute: int = 0
        self.day: int = 1
        self.month: int = 1
        self.year: int = 1
        self.current_time_period: str = "day"
        self.time_data: Dict[str, Any] = {}
        self.initialize_time()

    def initialize_time(self, game_time: Optional[float] = None):
        """Resets or initializes the time state."""
        self.game_time = self.initial_game_time if game_time is None else game_time
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
        day_name = self.day_names[(self.day - 1) % len(self.day_names)]
        month_name = self.month_names[(self.month - 1) % len(self.month_names)]
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
