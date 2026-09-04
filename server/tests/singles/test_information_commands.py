# tests/singles/test_information_commands.py
"""Coverage for engine/commands/information.py's time/calendar/weather/
skills handlers: their no-game/no-world guards, weather's indoors-vs-
outdoors branch and each known weather-type description plus the unknown-
weather fallback, and skills' no-player/no-skills guards and per-skill
progress-percentage display (including the max-level 100% case) --
previously almost entirely untested."""

from tests.fixtures import GameTestBase
from engine.commands.information import time_handler, calendar_handler, weather_handler, skills_handler
from engine.core.skill_system import MAX_SKILL_LEVEL


class TestTimeHandler(GameTestBase):
    def test_no_game_reports_unavailable(self):
        result = time_handler([], {"game": None})
        self.assertEqual("Time is unavailable.", result)

    def test_with_game_shows_time_and_date(self):
        result = time_handler([], {"game": self.game})
        self.assertIn("Current Time:", result)
        self.assertIn("Current Date:", result)
        self.assertIn("Time Period:", result)


class TestCalendarHandler(GameTestBase):
    def test_no_game_reports_unavailable(self):
        result = calendar_handler([], {"game": None})
        self.assertEqual("The calendar is unavailable.", result)

    def test_with_game_shows_calendar_details(self):
        result = calendar_handler([], {"game": self.game})
        self.assertIn("Day Names:", result)
        self.assertIn("Month Names:", result)


class TestWeatherHandler(GameTestBase):
    def test_no_game_reports_unknown(self):
        result = weather_handler([], {"game": None, "world": self.world})
        self.assertEqual("The weather is currently unknown.", result)

    def test_no_world_reports_unknown(self):
        result = weather_handler([], {"game": self.game, "world": None})
        self.assertEqual("The weather is currently unknown.", result)

    def test_indoors_reports_muffled_sounds(self):
        self.world.get_current_room(self.player).properties["outdoors"] = False
        self.game.weather_manager.current_weather = "storm"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("can't see the weather from inside", result)
        self.assertIn("storm", result)

    def test_no_current_room_defaults_outdoors(self):
        from unittest.mock import patch
        with patch.object(self.world, "get_room_for_player", return_value=None):
            self.game.weather_manager.current_weather = "clear"
            result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("Current Weather", result)

    def test_clear_weather_description(self):
        self.game.weather_manager.current_weather = "clear"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("clear and blue", result)

    def test_cloudy_weather_description(self):
        self.game.weather_manager.current_weather = "cloudy"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("Clouds fill the sky", result)

    def test_rain_weather_description(self):
        self.game.weather_manager.current_weather = "rain"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("Rain falls steadily", result)

    def test_storm_weather_description(self):
        self.game.weather_manager.current_weather = "storm"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("Thunder rumbles", result)

    def test_snow_weather_description(self):
        self.game.weather_manager.current_weather = "snow"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("Snowflakes drift", result)

    def test_unknown_weather_type_uses_fallback_description(self):
        self.game.weather_manager.current_weather = "totally_unknown_weather"
        result = weather_handler([], {"game": self.game, "world": self.world, "player": self.player})
        self.assertIn("unremarkable", result)


class TestSkillsHandler(GameTestBase):
    def test_no_player_reports_error(self):
        result = skills_handler([], {"player": None})
        self.assertEqual("Error.", result)

    def test_no_skills_reports_none_yet(self):
        self.player.runtime_state.progression.skills = {}
        result = skills_handler([], {"player": self.player})
        self.assertIn("no specialized skills yet", result)

    def test_skill_progress_percentage_shown(self):
        self.player.runtime_state.progression.skills = {
            "mining": {"level": 3, "xp": 10},
        }
        result = skills_handler([], {"player": self.player})
        self.assertIn("SKILLS", result)
        self.assertIn("Mining", result)
        self.assertIn("Level 3", result)

    def test_max_level_skill_shows_100_percent(self):
        self.player.runtime_state.progression.skills = {
            "mining": {"level": MAX_SKILL_LEVEL, "xp": 999999},
        }
        result = skills_handler([], {"player": self.player})
        self.assertIn("(100%)", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
