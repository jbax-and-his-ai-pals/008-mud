# engine/commands/information.py
from engine.commands.command_system import command
from engine.config import (
    FORMAT_TITLE, FORMAT_RESET, TIME_MONTHS_PER_YEAR,
    TIME_DAYS_PER_WEEK, TIME_DAYS_PER_MONTH
)
from engine.config.config_display import FORMAT_HIGHLIGHT
from engine.core.skill_system import MAX_SKILL_LEVEL, SkillSystem
from engine.items.resource_node import ResourceNode


@command("appraise", ["assess"], "information", "Inspect content-authored appraisal details for an item.\nUsage: appraise <item>")
def appraise_handler(args, context):
    """Show optional authored item knowledge without assuming an item genre."""
    player = context.get("player")
    if not player:
        return "You must start or load a game first."
    if not args:
        return "Appraise which item?"
    item = player.inventory.find_item_by_name(" ".join(args))
    if not item:
        return "You do not have that item."
    appraisal = item.get_property("appraisal")
    quality_score = item.get_property("material_quality_score", 0)
    has_material_grade = isinstance(quality_score, int) and not isinstance(quality_score, bool) and quality_score > 0
    if not isinstance(appraisal, dict) and not has_material_grade:
        return f"You find no notable appraisal details for the {item.name}."

    lines = [f"{FORMAT_TITLE}Appraisal: {item.name}{FORMAT_RESET}"]
    if isinstance(appraisal, dict):
        summary = str(appraisal.get("summary", "")).strip()
        if summary:
            lines.append(summary)
        for label, key in (("Quality", "quality"), ("Origin", "origin"), ("Craft", "craft")):
            value = str(appraisal.get(key, "")).strip()
            if value:
                lines.append(f"{label}: {value}")
        traits = appraisal.get("traits", [])
        if isinstance(traits, list):
            formatted_traits = [str(trait).strip() for trait in traits if str(trait).strip()]
            if formatted_traits:
                lines.append(f"Traits: {', '.join(formatted_traits)}")
    if has_material_grade:
        quality_label = str(item.get_property("material_quality_label", "notable")).strip() or "notable"
        lines.append(f"Material grade: {quality_label} (score {quality_score})")
        source = str(item.get_property("material_source_label", "")).strip()
        if source:
            lines.append(f"Gathered from: {source}")
    return "\n".join(lines)


@command("survey", ["resources"], "information", "Survey gatherable resources in the current area.", content_capability="gathering")
def survey_handler(args, context):
    """Present authored resource-node state in a player-facing, neutral form."""
    world = context.get("world")
    player = context.get("player")
    if not world or not player:
        return "You must start or load a game first."
    room = world.get_room_for_player(player)
    if room is None:
        return "There is nowhere here to survey."
    nodes = [item for item in room.items if isinstance(item, ResourceNode)]
    if not nodes:
        return "You find no gatherable resources here."
    time_manager = getattr(getattr(world, "game", None), "time_manager", None)
    current_season = str(getattr(time_manager, "time_data", {}).get("season", "")).strip()
    lines = [f"{FORMAT_TITLE}Resource Survey{FORMAT_RESET}"]
    for node in nodes:
        charges = node.available_charges(world)
        maximum = int(node.get_property("max_charges", charges))
        required_tool = str(node.get_property("tool_required", "none")).replace("_", " ")
        respawn_days = int(node.get_property("respawn_days", 0))
        seasons = node.get_property("seasons", [])
        seasonal_note = ""
        if isinstance(seasons, list) and seasons:
            names = ", ".join(str(season) for season in seasons)
            seasonal_note = f"; seasons: {names}"
            if current_season and current_season not in seasons:
                seasonal_note += " (inactive now)"
        recovery_note = f"; recovers in {respawn_days} day(s)" if respawn_days > 0 else ""
        material_quality = node.get_property("material_quality", {})
        quality_note = ""
        if isinstance(material_quality, dict) and isinstance(material_quality.get("score"), int) and material_quality["score"] > 0:
            quality_note = f"; material quality: {material_quality.get('label', material_quality.get('id', 'notable'))}"
        state = "ready" if charges > 0 else "depleted"
        lines.append(f"- {node.name}: {charges}/{maximum} ({state}); tool: {required_tool}{recovery_note}{seasonal_note}{quality_note}")
    return "\n".join(lines)

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
