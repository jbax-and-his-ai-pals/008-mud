# engine/commands/information.py
from engine.commands.command_system import command
from engine.config import (
    FORMAT_TITLE, FORMAT_RESET, TIME_MONTHS_PER_YEAR,
    TIME_DAYS_PER_WEEK, TIME_DAYS_PER_MONTH
)
from engine.config.config_display import FORMAT_HIGHLIGHT
from engine.core.skill_system import MAX_SKILL_LEVEL, SkillSystem

@command("time", ["clock"], "information", "Display the current in-game time and date.")
def time_handler(args, context):
    """Time command handler."""
    game = context.get("game")
    if not game:
        return "Time is unavailable."

    time_data = game.time_manager.time_data
    response = f"{FORMAT_TITLE}Current Time:{FORMAT_RESET} {time_data.get('time_str', 'N/A')}\n"
    response += f"{FORMAT_TITLE}Current Date:{FORMAT_RESET} {time_data.get('date_str', 'N/A')}\n"
    response += f"{FORMAT_TITLE}Time Period:{FORMAT_RESET} {time_data.get('time_period', 'N/A').capitalize()}\n"
    
    return response

@command("calendar", ["cal", "date"], "information", "Display the in-game calendar details.")
def calendar_handler(args, context):
    """Calendar command handler."""
    game = context.get("game")
    if not game:
        return "The calendar is unavailable."
        
    time_data = game.time_manager.time_data
    
    response = f"{FORMAT_TITLE}Current Date:{FORMAT_RESET} {time_data.get('date_str', 'N/A')}\n\n"
    response += f"Days in a week: {TIME_DAYS_PER_WEEK}\n"
    response += f"Days in a month: {TIME_DAYS_PER_MONTH}\n"
    response += f"Months in a year: {TIME_MONTHS_PER_YEAR}\n\n"
    
    response += f"{FORMAT_TITLE}Day Names:{FORMAT_RESET}\n" + ", ".join(game.time_manager.day_names) + "\n\n"
    response += f"{FORMAT_TITLE}Month Names:{FORMAT_RESET}\n" + ", ".join(game.time_manager.month_names) + "\n"
    
    return response

@command("weather", ["forecast"], "information", "Check the current weather conditions.")
def weather_handler(args, context):
    """Weather command handler."""
    game = context.get("game")
    world = context.get("world")
    if not game or not world:
        return "The weather is currently unknown."

    weather_manager = game.weather_manager
    player = context.get("player")
    current_room = world.get_room_for_player(player)
    is_outdoors = current_room.properties.get("outdoors", True) if current_room else True

    if not is_outdoors:
        return f"You can't see the weather from inside, but you can hear sounds indicating {weather_manager.current_weather} conditions outside."
    
    # Content sets provide their own per-weather-type flavor text via a
    # "weather.descriptions" ruleset section; this default is a plain,
    # theme-neutral fallback.
    default_weather_descriptions = {
        "clear": "The sky is clear and blue.",
        "cloudy": "Clouds fill the sky.",
        "rain": "Rain falls steadily.",
        "storm": "Thunder rumbles as a storm rages.",
        "snow": "Snowflakes drift down from the sky."
    }
    weather_descriptions = world.ruleset_section("weather").get("descriptions") or default_weather_descriptions
    description = weather_descriptions.get(weather_manager.current_weather, "The weather is unremarkable.")
    
    return f"Current Weather: {weather_manager.current_weather.capitalize()} ({weather_manager.current_intensity})\n\n{description}"

@command("skills", [], "information", "List your current skill levels.", ruleset_system="progression")
def skills_handler(args, context):
    player = context.get("player")
    if not player: return "Error."
    
    if not player.runtime_state.progression.skills:
        return "You have no specialized skills yet."
        
    msg = [f"{FORMAT_TITLE}SKILLS{FORMAT_RESET}"]
    for name, data in player.runtime_state.progression.skills.items():
        lvl = data.get("level", 0)
        xp = data.get("xp", 0)
        
        # Calculate progress to next level
        req = SkillSystem.get_xp_for_next_level(lvl)
        pct = int((xp / req) * 100) if lvl < MAX_SKILL_LEVEL else 100
        
        msg.append(f"- {FORMAT_HIGHLIGHT}{name.capitalize()}{FORMAT_RESET}: Level {lvl} ({pct}%)")
        
    return "\n".join(msg)
