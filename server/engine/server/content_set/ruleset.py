"""The simple ruleset sections, retired keys, room and region property keys, crime and debug rules.

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
from .abilities import (_ability_ids)
from .core import (ContentSetIssue, _json_kind, _load_json)
from .definitions import (_load_definition_ids)
from .npcs import (_SIMPLE_RULESET_SECTION_KEYS)
from .references import (_format_placeholders)


def _validate_simple_ruleset_sections(
    content_root: Path, ruleset: Any, issues: list[ContentSetIssue], ruleset_path: Path | None = None,
) -> None:
    """Seven small ruleset sections the engine reads leniently.

    Each reader falls back without a word on a value it cannot use -- a calendar
    with an empty or non-string name reverts to the default names, a start time
    out of range starts at midnight, a misspelt key is simply never read -- and
    two raise: `elites.name_pattern` and `npc_naming.random_name_pattern` are
    `str.format`ted with fixed fields, so any other placeholder is a KeyError the
    first time an elite or a randomly named NPC spawns.
    """
    if not isinstance(ruleset, dict):
        return
    source = str(ruleset_path or "ruleset")

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", source, message))

    def warn(message: str) -> None:
        issues.append(ContentSetIssue("warning", source, message))

    def strings(value: Any, label: str, *, allow_empty_list: bool = False) -> bool:
        if not isinstance(value, list) or (not value and not allow_empty_list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in value
        ):
            error(f"{label} must be a {'' if allow_empty_list else 'non-empty '}array of non-empty strings")
            return False
        return True

    def number(value: Any, label: str, *, low: float, high: float | None = None, low_inclusive: bool = True) -> None:
        in_range = (value >= low if low_inclusive else value > low) if isinstance(value, (int, float)) else False
        ok = not isinstance(value, bool) and isinstance(value, (int, float)) and in_range and (high is None or value <= high)
        if not ok:
            if high is not None:
                bound = f"from {low} to {high}"
            else:
                bound = f"of at least {low}" if low_inclusive else f"greater than {low}"
            error(f"{label} must be a number {bound}")

    def pattern(value: Any, label: str, fields: set[str]) -> None:
        if not isinstance(value, str) or not value.strip():
            error(f"{label} must be a non-empty string")
            return
        extra = _format_placeholders(value) - fields
        if extra:
            allowed = ", ".join("{" + field + "}" for field in sorted(fields))
            error(f"{label} uses unknown placeholder(s) {sorted(extra)}; only {allowed} are filled in, and any other raises when it is used")

    sections: dict[str, dict[str, Any]] = {}
    for name, known in _SIMPLE_RULESET_SECTION_KEYS.items():
        if name not in ruleset:
            continue
        section = ruleset[name]
        if not isinstance(section, dict):
            error(f"{name} must be an object")
            continue
        sections[name] = section
        for key in section:
            if not str(key).startswith("_") and key not in known:
                error(f"{name}.{key} is not a setting the engine reads (known: {', '.join(known)})")

    locksmithing = sections.get("locksmithing", {})
    if "skill" in locksmithing:
        skill = locksmithing["skill"]
        if not isinstance(skill, str):
            error("locksmithing.skill must be a string (empty means locks cannot be picked)")
        else:
            skills = ruleset.get("skills")
            bonuses = skills.get("stat_bonuses") if isinstance(skills, dict) else None
            if skill.strip() and isinstance(bonuses, dict) and bonuses and skill.strip() not in bonuses:
                warn(f"locksmithing.skill '{skill}' has no skills.stat_bonuses rule, so no stat backs lockpicking")

    economy = sections.get("economy", {})
    if "currency_name" in economy and (not isinstance(economy["currency_name"], str) or not economy["currency_name"].strip()):
        error("economy.currency_name must be a non-empty string")

    calendar = sections.get("calendar", {})
    for key in ("day_names", "month_names"):
        if key in calendar and strings(calendar[key], f"calendar.{key}"):
            repeated = sorted({name for name in calendar[key] if calendar[key].count(name) > 1})
            if repeated:
                error(f"calendar.{key} repeats {repeated}")
    if "start_time" in calendar:
        start = calendar["start_time"]
        if not isinstance(start, dict):
            error("calendar.start_time must be an object with hour and minute")
        else:
            for key, high in (("hour", 23), ("minute", 59)):
                value = start.get(key, 0)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= high:
                    error(f"calendar.start_time.{key} must be an integer from 0 to {high} (otherwise the clock starts at noon)")

    spawning = sections.get("spawning", {})
    if "no_spawn_keywords" in spawning and strings(spawning["no_spawn_keywords"], "spawning.no_spawn_keywords", allow_empty_list=True):
        room_text: list[str] = []
        for region_path in sorted((content_root / "regions").glob("*.json")):
            region = _load_json(region_path, [], "region definitions")
            rooms = region.get("rooms", {}) if isinstance(region, dict) else {}
            if isinstance(rooms, dict):
                for room_id, room in rooms.items():
                    room_text.append(str(room_id).lower())
                    if isinstance(room, dict):
                        room_text.append(str(room.get("name", "")).lower())
        for keyword in spawning["no_spawn_keywords"]:
            if room_text and not any(keyword.lower() in text for text in room_text):
                warn(f"spawning.no_spawn_keywords '{keyword}' matches no room id or name, so it protects nothing")

    for key, template in sections.get("messages", {}).items():
        if str(key).startswith("_") or key not in MESSAGES:
            continue
        for problem in template_problems(template, key):
            error(f"messages.{key}: {problem}")

    companions = sections.get("companions", {})
    if "max" in companions:
        value = companions["max"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            error("companions.max must be a whole number of 0 or more (0 means no companions in this world)")

    elites = sections.get("elites", {})
    for key in ("chance", "loot_guaranteed_chance"):
        if key in elites:
            number(elites[key], f"elites.{key}", low=0, high=1)
    for key in ("stat_multiplier", "loot_quantity_multiplier"):
        if key in elites:
            number(elites[key], f"elites.{key}", low=0, low_inclusive=False)
    if "name_pattern" in elites:
        pattern(elites["name_pattern"], "elites.name_pattern", {"prefix", "name"})
    if "prefixes" in elites:
        strings(elites["prefixes"], "elites.prefixes")

    defaults = sections.get("player_defaults", {})
    if "player_class" in defaults and (not isinstance(defaults["player_class"], str) or not defaults["player_class"].strip()):
        error("player_defaults.player_class must be a non-empty string")
    if "magic" in defaults:
        magic = defaults["magic"]
        if not isinstance(magic, dict):
            error("player_defaults.magic must be an object")
        elif "known_spells" in magic and strings(magic["known_spells"], "player_defaults.magic.known_spells", allow_empty_list=True):
            ability_ids = _ability_ids(content_root, issues)
            for spell_id in magic["known_spells"]:
                if spell_id.strip() not in ability_ids:
                    error(f"player_defaults.magic.known_spells references missing ability '{spell_id}'")
    if "starting_inventory" in defaults:
        entries = defaults["starting_inventory"]
        if not isinstance(entries, list):
            error("player_defaults.starting_inventory must be an array")
        else:
            item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
            for index, entry in enumerate(entries):
                label = f"player_defaults.starting_inventory[{index}]"
                if isinstance(entry, str):
                    item_id = entry.strip()
                elif isinstance(entry, dict):
                    item_id = str(entry.get("item_id", "")).strip()
                    quantity = entry.get("quantity", 1)
                    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                        error(f"{label}.quantity must be a positive integer (anything else stops character creation)")
                    if "equip" in entry and not isinstance(entry["equip"], bool):
                        error(f"{label}.equip must be true or false (true: the character starts wearing it)")
                    for extra in entry:
                        if extra not in ("item_id", "quantity", "equip"):
                            error(f"{label}.{extra} is not read (known: item_id, quantity, equip)")
                else:
                    error(f"{label} must be an item id or an object with item_id and quantity")
                    continue
                if item_id not in item_ids:
                    error(f"{label} references missing item '{item_id}' (the engine skips it and the player starts without it)")

    # `World._attempt_combat_retreat` adds these numbers without a check, so a
    # quoted one raises the first time a player tries to leave a fight.
    combat = sections.get("combat", {})
    retreat = combat.get("retreat")
    if retreat is not None:
        if not isinstance(retreat, dict):
            error("combat.retreat must be an object")
        else:
            for key in retreat:
                if key not in ("skill", "base_difficulty", "difficulty_per_hostile_level"):
                    error(f"combat.retreat.{key} is not read (known: skill, base_difficulty, difficulty_per_hostile_level)")
            if "skill" in retreat and not isinstance(retreat["skill"], str):
                error("combat.retreat.skill must be a string (empty means retreat always succeeds)")
            for key in ("base_difficulty", "difficulty_per_hostile_level"):
                if key in retreat:
                    number(retreat[key], f"combat.retreat.{key}", low=0)
    sharing = combat.get("experience_sharing")
    if sharing is not None:
        from engine.core.kill_credit import EXPERIENCE_SHARING_MODES

        if not isinstance(sharing, dict):
            error("combat.experience_sharing must be an object")
        else:
            for key in sharing:
                if key not in ("mode", "min_share", "memory_seconds"):
                    error(f"combat.experience_sharing.{key} is not read (known: mode, min_share, memory_seconds)")
            if "mode" in sharing and sharing["mode"] not in EXPERIENCE_SHARING_MODES:
                error(f"combat.experience_sharing.mode {sharing['mode']!r} is not a way to share experience, so the default (proportional) applies (known: {', '.join(EXPERIENCE_SHARING_MODES)})")
            if "min_share" in sharing:
                value = sharing["min_share"]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 1:
                    error("combat.experience_sharing.min_share must be a number from 0 up to (not including) 1: the least share of the damage that makes a player a participant")
            if "memory_seconds" in sharing:
                value = sharing["memory_seconds"]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    error("combat.experience_sharing.memory_seconds must be a number of seconds, 0 or more (0: a blow is never forgotten): how long a blow counts toward a kill")
    for key in ("additional_blocked_command_names", "additional_combat_message_tokens"):
        if key in combat:
            strings(combat[key], f"combat.{key}", allow_empty_list=True)

    status = sections.get("status", {})
    if "stats" in status and strings(status["stats"], "status.stats", allow_empty_list=True):
        repeated = sorted({stat for stat in status["stats"] if status["stats"].count(stat) > 1})
        if repeated:
            error(f"status.stats repeats {repeated}")

    naming = sections.get("npc_naming", {})
    if "first_names" in naming and strings(naming["first_names"], "npc_naming.first_names"):
        repeated = sorted({name for name in naming["first_names"] if naming["first_names"].count(name) > 1})
        if repeated:
            warn(f"npc_naming.first_names lists {repeated} more than once, which makes each of them twice as likely")
    if "random_name_pattern" in naming:
        pattern(naming["random_name_pattern"], "npc_naming.random_name_pattern", {"first_name", "title"})


_CRIME_KEYS = {
    "": ("enabled", "witness", "consequences", "custody"),
    "witness": ("skill", "base_difficulty", "rank_attribute", "rank_multiplier", "authority_property",
                "authority_bonus", "excluded_factions", "xp_success", "xp_caught"),
    "consequences": ("reputation_key", "reputation_per_value", "custody_value_threshold", "custody_cumulative_threshold",
                     "custody_reputation_threshold", "fine_rate", "fine_minimum"),
    "custody": ("room_property", "release_destination_property", "base_seconds", "seconds_per_value",
                "concealed_tool_requirements", "emergency_tool_item_id", "emergency_tool_durability",
                "escape_alert_margin", "escape_sentence_penalty_seconds", "search_success_chance",
                "search_currency_min", "search_currency_max"),
}
# Numbers that must not be negative; `custody_reputation_threshold` is a
# reputation floor and may be.
_CRIME_NON_NEGATIVE = {
    "witness": ("base_difficulty", "rank_multiplier", "authority_bonus", "xp_success", "xp_caught"),
    "consequences": ("reputation_per_value", "custody_value_threshold", "custody_cumulative_threshold", "fine_rate", "fine_minimum"),
    "custody": ("base_seconds", "seconds_per_value", "escape_alert_margin", "escape_sentence_penalty_seconds"),
}


def _validate_room_property_keys(content_root: Path, ruleset: Any, issues: list[ContentSetIssue]) -> None:
    """A room's `properties` against what reads them (`room.py` ROOM_PROPERTY_KINDS).

    The bag is open, so a key nothing reads is kept and does nothing: a
    warning, since a plugin might read it. A read key of the wrong type is an
    error, and so is a `locked_by` naming no item (the door can never open).
    The ruleset's custody section names two more keys.
    """
    from engine.world.room import ROOM_EDITOR_PROPERTY_KINDS, ROOM_PROPERTY_KINDS

    kinds = {**ROOM_PROPERTY_KINDS, **ROOM_EDITOR_PROPERTY_KINDS}
    custody = ((ruleset.get("crime") or {}).get("custody") or {}) if isinstance(ruleset, dict) and isinstance(ruleset.get("crime"), dict) else {}
    if isinstance(custody, dict):
        if isinstance(custody.get("room_property"), str) and custody["room_property"].strip():
            kinds[custody["room_property"].strip()] = "boolean"
        release = custody.get("release_destination_property", "release_destination")
        if isinstance(release, str) and release.strip():
            kinds[release.strip()] = "string"
    item_ids = _load_definition_ids(content_root / "items", "item definitions", [])
    known = ", ".join(sorted(kinds))
    for path in sorted((content_root / "regions").glob("*.json")):
        region = _load_json(path, [], "region definitions")
        if not isinstance(region, dict) or not isinstance(region.get("rooms"), dict):
            continue
        region_id = str(region.get("region_id", path.stem))
        for room_id, room in region["rooms"].items():
            properties = room.get("properties") if isinstance(room, dict) else None
            if not isinstance(properties, dict):
                continue
            label = f"room '{region_id}:{room_id}' properties"
            for key, value in properties.items():
                if str(key).startswith("_"):
                    continue
                kind = kinds.get(key)
                if kind is None:
                    issues.append(ContentSetIssue("warning", str(path), f"{label}.{key} is read by nothing, so it does nothing (known: {known})"))
                    continue
                if _json_kind(value) != kind:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{key} must be a {kind} (got {_json_kind(value)})"))
                    continue
                if key == "temperature" and value not in ("normal", "cold", "hot"):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.temperature must be normal, cold, or hot"))
                if key == "locked_by" and value and value not in item_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.locked_by references missing item '{value}', so the room can never be entered"))


def _validate_region_property_keys(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A region's `properties`, and each district's fields, against what reads
    them (`region.py`). As for rooms: a key nothing reads is a warning, a read
    key of the wrong type an error. The editor's own district fields are known.
    """
    from engine.world.region import DISTRICT_EDITOR_KEYS, DISTRICT_PROPERTY_KINDS, REGION_PROPERTY_KINDS

    def check(values: dict, kinds: dict, extra: tuple, label: str, path: Path) -> None:
        for key, value in values.items():
            if str(key).startswith("_") or key in extra:
                continue
            kind = kinds.get(key)
            if kind is None:
                issues.append(ContentSetIssue("warning", str(path), f"{label}.{key} is read by nothing, so it does nothing (known: {', '.join(sorted(kinds))})"))
            elif _json_kind(value) != kind:
                issues.append(ContentSetIssue("error", str(path), f"{label}.{key} must be a {kind} (got {_json_kind(value)})"))
            elif key == "temperature" and value not in ("normal", "cold", "hot"):
                issues.append(ContentSetIssue("error", str(path), f"{label}.temperature must be normal, cold, or hot"))

    for path in sorted((content_root / "regions").glob("*.json")):
        region = _load_json(path, [], "region definitions")
        if not isinstance(region, dict) or not isinstance(region.get("rooms"), dict):
            continue
        region_id = str(region.get("region_id", path.stem))
        properties = region.get("properties")
        if not isinstance(properties, dict):
            continue
        check(properties, REGION_PROPERTY_KINDS, (), f"region '{region_id}' properties", path)
        districts = properties.get("districts")
        if isinstance(districts, dict):
            for district_id, district in districts.items():
                if isinstance(district, dict):
                    check(district, DISTRICT_PROPERTY_KINDS, DISTRICT_EDITOR_KEYS, f"region '{region_id}' district '{district_id}'", path)


# Ruleset keys that were read by nothing and have been removed. Refused rather
# than ignored, so an author is not left setting a value that changes nothing.
_RETIRED_RULESET_KEYS = {
    "ruleset_id": "the manifest's `id` names the content set",
    "world_mode": "the world mode is the server's (the feature profile's `world.mode`), not the content set's",
}


def _refuse_retired_ruleset_keys(ruleset: Any, issues: list[ContentSetIssue], ruleset_path: Path | None = None) -> None:
    if not isinstance(ruleset, dict):
        return
    for key, reason in _RETIRED_RULESET_KEYS.items():
        if key in ruleset:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path or "ruleset"),
                f"ruleset.{key} is not read by anything and has been removed; {reason}. Delete it",
            ))


def _validate_crime_and_debug_rules(
    content_root: Path, ruleset: Any, issues: list[ContentSetIssue], ruleset_path: Path | None = None,
) -> None:
    """`crime` (`core/crime_manager.py`, `commands/jail.py`, `world.py`) and `debug`.

    `CrimeManager._number` turns any value that is not a number into 0, and
    `is_enabled` wants the boolean `true`, so a quoted number or `"true"` changes
    the law without a word. With crime enabled, a `custody.room_property` no room
    carries confiscates the player's pack and then leaves them where they stood.
    """
    if not isinstance(ruleset, dict):
        return
    source = str(ruleset_path or "ruleset")

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", source, message))

    def is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    crime = ruleset.get("crime")
    if crime is not None:
        if not isinstance(crime, dict):
            error("crime must be an object")
            crime = {}
        parts: dict[str, dict[str, Any]] = {"": crime}
        for name in ("witness", "consequences", "custody"):
            value = crime.get(name, {})
            if not isinstance(value, dict):
                error(f"crime.{name} must be an object")
                value = {}
            parts[name] = value
        for name, part in parts.items():
            prefix = f"crime.{name}" if name else "crime"
            for key in part:
                if not str(key).startswith("_") and key not in _CRIME_KEYS[name]:
                    error(f"{prefix}.{key} is not a setting the engine reads (known: {', '.join(_CRIME_KEYS[name])})")
        for name, keys in _CRIME_NON_NEGATIVE.items():
            for key in keys:
                if key in parts[name] and (not is_number(parts[name][key]) or parts[name][key] < 0):
                    error(f"crime.{name}.{key} must be a non-negative number (anything else counts as 0)")
        consequences, witness, custody = parts["consequences"], parts["witness"], parts["custody"]
        if "custody_reputation_threshold" in consequences and not is_number(consequences["custody_reputation_threshold"]):
            error("crime.consequences.custody_reputation_threshold must be a number (anything else counts as 0)")
        if "enabled" in crime and not isinstance(crime["enabled"], bool):
            error("crime.enabled must be true or false (anything else leaves crime off)")
        for key in ("rank_attribute", "authority_property", "skill"):
            if key in witness and not isinstance(witness[key], str):
                error(f"crime.witness.{key} must be a string")
        if "excluded_factions" in witness and (
            not isinstance(witness["excluded_factions"], list)
            or any(not isinstance(f, str) or not f.strip() for f in witness["excluded_factions"])
        ):
            error("crime.witness.excluded_factions must be an array of faction ids (otherwise nobody is excluded)")
        chance = custody.get("search_success_chance")
        if chance is not None and (not is_number(chance) or not 0 <= chance <= 1):
            error("crime.custody.search_success_chance must be a number from 0 to 1")
        low, high = custody.get("search_currency_min", 0), custody.get("search_currency_max", custody.get("search_currency_min", 0))
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (low, high)):
            error("crime.custody.search_currency_min and search_currency_max must be non-negative integers")
        elif low > high:
            error(f"crime.custody.search_currency_min ({low}) is greater than search_currency_max ({high})")
        if "emergency_tool_durability" in custody:
            durability = custody["emergency_tool_durability"]
            if isinstance(durability, bool) or not isinstance(durability, int) or durability < 1:
                error("crime.custody.emergency_tool_durability must be a positive integer")
        if "emergency_tool_item_id" in custody:
            item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
            if custody["emergency_tool_item_id"] not in item_ids:
                error(f"crime.custody.emergency_tool_item_id references missing item '{custody['emergency_tool_item_id']}' (the concealed tool is silently not given)")
        requirements = custody.get("concealed_tool_requirements", [])
        if not isinstance(requirements, list) or any(
            not isinstance(entry, dict) or not isinstance(entry.get("skill"), str) or not entry.get("skill", "").strip()
            or not is_number(entry.get("minimum", 0))
            for entry in requirements
        ):
            error("crime.custody.concealed_tool_requirements must be an array of {skill, minimum}")

        if crime.get("enabled") is True:
            for label, part, key in (("crime.witness.skill", witness, "skill"),
                                     ("crime.consequences.reputation_key", consequences, "reputation_key"),
                                     ("crime.custody.room_property", custody, "room_property")):
                if not isinstance(part.get(key), str) or not part.get(key, "").strip():
                    error(f"{label} is required while crime is enabled")
            room_property = custody.get("room_property")
            if isinstance(room_property, str) and room_property.strip():
                cells = 0
                for region_path in sorted((content_root / "regions").glob("*.json")):
                    region = _load_json(region_path, [], "region definitions")
                    rooms = region.get("rooms", {}) if isinstance(region, dict) else {}
                    for room in (rooms.values() if isinstance(rooms, dict) else []):
                        if isinstance(room, dict) and isinstance(room.get("properties"), dict) and room["properties"].get(room_property):
                            cells += 1
                if cells == 0:
                    error(
                        f"crime.custody.room_property '{room_property}' references a missing jail room (no room sets it), "
                        "so a jailed player keeps their position after their pack is confiscated"
                    )

    debug = ruleset.get("debug")
    if debug is None:
        return
    if not isinstance(debug, dict):
        error("debug must be an object")
        return
    known = ("gear_item_ids", "spawnable_stations", "lock_test_spells")
    for key in debug:
        if not str(key).startswith("_") and key not in known:
            error(f"debug.{key} is not a setting the engine reads (known: {', '.join(known)})")
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    gear = debug.get("gear_item_ids", [])
    if not isinstance(gear, list):
        error("debug.gear_item_ids must be an array of item ids")
    else:
        for item_id in gear:
            if item_id not in item_ids:
                error(f"debug.gear_item_ids references missing item '{item_id}'")
    stations = debug.get("spawnable_stations", {})
    if not isinstance(stations, dict):
        error("debug.spawnable_stations must be an object of station -> item id")
    else:
        for station, item_id in stations.items():
            if item_id not in item_ids:
                error(f"debug.spawnable_stations.{station} references missing item '{item_id}'")
    spells = debug.get("lock_test_spells", [])
    if not isinstance(spells, list):
        error("debug.lock_test_spells must be an array of ability ids")
    elif spells:
        ability_ids = _ability_ids(content_root, issues)
        for spell_id in spells:
            if spell_id not in ability_ids:
                error(f"debug.lock_test_spells references missing ability '{spell_id}'")


_THEME_KEYS = ("name_templates", "description", "room_names", "room_descriptions", "spawner")
_THEME_FORMATTED_LISTS = ("name_templates", "room_descriptions")
_THEME_LITERAL_LISTS = ("room_names",)
