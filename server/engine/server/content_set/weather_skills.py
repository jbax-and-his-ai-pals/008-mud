"""Skills rules and weather: shapes, chances and profiles.

Part of the content-set validator package (`engine/server/content_set/`); see `__init__.py`.
"""

from __future__ import annotations

import copy
import os
import json
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from engine import conditions as _conditions
from engine.utils.messages import MESSAGES, template_problems
from .core import (ContentSetIssue, _load_json)


def _validate_skills_rules(ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """`skills.stat_bonuses` maps a skill to the stat that backs it.

    Only shapes are checked here, not whether the stat exists: the ruleset is
    where a set declares which stats it has, so `stat: "grit"` here *defines*
    grit, and telling an author their own vocabulary is wrong would be the check
    inventing a finding. The mismatch that matters is across files -- a
    background or a resource pool naming a stat the ruleset never declared --
    and `_validate_background_stats` is what catches that.
    """
    skills = ruleset.get("skills")
    if skills is None:
        return
    if not isinstance(skills, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "skills must be an object"))
        return
    bonuses = skills.get("stat_bonuses", {})
    if not isinstance(bonuses, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "skills.stat_bonuses must be an object"))
        return
    for skill, rule in sorted(bonuses.items()):
        if str(skill).startswith("_"):
            continue
        label = f"skills.stat_bonuses.{skill}"
        if not isinstance(rule, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            continue
        stat = rule.get("stat")
        if stat is not None and (not isinstance(stat, str) or not stat.strip()):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.stat must be a non-empty string"))


def _validate_weather_shapes(ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """`weather.descriptions` and each profile's `map`/`travel_notes`.

    Weather types are this ruleset's own open vocabulary -- whatever
    `weather.chances` or a profile's own `map` names -- so nothing here checks a
    type against a closed list. What is checked is the shape every reader
    assumes: `information.py`'s `weather` command indexes `descriptions` by
    type and expects a string back, and `WeatherManager.effective_weather`/
    `travel_note` do the same for a profile's `map`/`travel_notes`. A non-string
    value there is not a "no flavor text" case, it is a crash the next time
    that weather rolls.
    """
    weather = ruleset.get("weather")
    if not isinstance(weather, dict):
        return

    def string_map_issues(value: Any, label: str) -> None:
        if not isinstance(value, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            return
        for key, mapped in value.items():
            if str(key).startswith("_"):
                continue
            if not isinstance(mapped, str):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.{key} must be a string"))

    if "descriptions" in weather:
        string_map_issues(weather["descriptions"], "weather.descriptions")

    profiles = weather.get("profiles", {})
    if isinstance(profiles, dict):
        for profile_id, profile in profiles.items():
            if str(profile_id).startswith("_"):
                continue
            label = f"weather.profiles.{profile_id}"
            if not isinstance(profile, dict):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
                continue
            if "map" in profile:
                string_map_issues(profile["map"], f"{label}.map")
            if "travel_notes" in profile:
                string_map_issues(profile["travel_notes"], f"{label}.travel_notes")

    if "chances" in weather:
        _validate_weather_chances(weather["chances"], issues, ruleset_path)


def _validate_weather_chances(chances: Any, issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """`weather.chances`: per season, the weather types and their weights.

    `WeatherManager._update_weather` reads `chances.get(season, chances["summer"])`
    -- the summer fallback is evaluated on every roll, so a table without it
    raises on the first weather change, whatever the season. A season that is not
    a table raises too. A bad weight is caught there and the weather quietly
    becomes "clear"; a season the calendar never produces is never read. Every
    key in a season is a weather type (`_` keys included: nothing skips them).
    """
    from engine.core.time_manager import SEASONS

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(ruleset_path), message))

    if not isinstance(chances, dict):
        error("weather.chances must be an object of seasons")
        return
    if not chances:
        return
    seasons = [key for key in chances if not str(key).startswith("_")]
    for season in seasons:
        if season not in SEASONS:
            error(f"weather.chances.{season} is not a season the calendar produces ({', '.join(SEASONS)})")
    if "summer" not in chances:
        error("weather.chances needs a summer table: a season it omits uses summer's, and the engine looks summer up on every weather change")
    for season in seasons:
        table = chances[season]
        label = f"weather.chances.{season}"
        if not isinstance(table, dict) or not table:
            error(f"{label} must be a non-empty object of weather type to weight")
            continue
        positive = False
        for weather_type, weight in table.items():
            if not str(weather_type).strip():
                error(f"{label} has an empty weather type")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
                error(f"{label}.{weather_type} must be a weight of 0 or more")
            elif weight > 0:
                positive = True
        if not positive:
            error(f"{label} needs at least one weight above 0")


def _validate_weather_profiles(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """A `weather_profile` a region selects must be one the ruleset declares.

    `WeatherManager` looks the id up and falls back to the unmapped global
    weather, which is a reasonable default and also completely invisible: a
    region authored to have alpine weather just reports rain.
    """
    _validate_weather_shapes(ruleset, issues, ruleset_path)
    weather = ruleset.get("weather")
    profiles = weather.get("profiles", {}) if isinstance(weather, dict) else {}
    declared = {
        str(profile_id) for profile_id in profiles
    } if isinstance(profiles, dict) else set()
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return
    for path in sorted(region_dir.glob("*.json")):
        payload = _load_json(path, [], "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            continue
        profile_id = properties.get("weather_profile")
        if not isinstance(profile_id, str) or not profile_id.strip():
            continue
        if profile_id.strip() in declared:
            continue
        issues.append(ContentSetIssue(
            "error",
            str(path),
            "properties.weather_profile names '%s', which ruleset weather.profiles "
            "does not declare%s" % (
                profile_id.strip(),
                "" if declared else " (it declares no profiles at all)",
            ),
        ))


_QUEST_TEXT_TEMPLATE_TYPES = ("kill", "fetch", "deliver")
_QUEST_TEXT_TEMPLATE_FIELDS = (
    "giver_name", "quantity", "target_name_plural", "location_description",
    "item_name_plural", "source_enemy_name_plural", "item_to_deliver_name",
    "recipient_name", "recipient_location_description",
)
