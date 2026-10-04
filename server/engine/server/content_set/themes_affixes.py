"""Dynamic region themes, item affixes, resistances and sets.

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
from .definitions import (_load_definition_ids)
from .references import (_format_placeholders)
from .ruleset import (_THEME_FORMATTED_LISTS, _THEME_KEYS, _THEME_LITERAL_LISTS)


def _validate_dynamic_themes(content_root: Path, ruleset: Any, issues: list[ContentSetIssue], ruleset_path: Path | None = None) -> None:
    """`regions/dynamic_themes.json` (`world/region_generator.py`).

    A quest's procedural region, and the ruleset's
    `quest_generation.instance_quest.default_procedural_theme`, name a theme
    here; a name with no theme builds no region at all. The generator replaces
    `{Key}`/`{key}` for each placeholder list and nothing else, so any other brace
    reaches the player as written -- and `room_names` and `description` are never
    formatted. An empty name or description list raises inside `random.choice`,
    and a spawner monster with no NPC template is skipped without a word.
    """
    path = content_root / "regions" / "dynamic_themes.json"
    themes: dict[str, Any] = {}
    source = str(path)

    def error(message: str, where: str = source) -> None:
        issues.append(ContentSetIssue("error", where, message))

    if path.is_file():
        payload = _load_json(path, issues, "dynamic themes")
        if isinstance(payload, dict):
            for key in payload:
                if not str(key).startswith("_") and key not in ("themes", "placeholders"):
                    error(f"'{key}' is not read (known: themes, placeholders)")
            placeholders = payload.get("placeholders", {})
            if not isinstance(placeholders, dict):
                error("placeholders must be an object of name -> word list")
                placeholders = {}
            for name, words in placeholders.items():
                if not isinstance(words, list) or not words or any(not isinstance(w, str) or not w.strip() for w in words):
                    error(f"placeholders.{name} must be a non-empty array of words")
            tokens = {f"{{{name.capitalize()}}}" for name in placeholders} | {f"{{{name.lower()}}}" for name in placeholders}
            raw_themes = payload.get("themes", {})
            if not isinstance(raw_themes, dict):
                error("themes must be an object of theme name -> theme")
                raw_themes = {}
            npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
            for theme_name, theme in raw_themes.items():
                label = f"themes.{theme_name}"
                if not isinstance(theme, dict):
                    error(f"{label} must be an object")
                    continue
                themes[theme_name] = theme
                for key in theme:
                    if not str(key).startswith("_") and key not in _THEME_KEYS:
                        error(f"{label}.{key} is not read (known: {', '.join(_THEME_KEYS)})")
                for key in _THEME_FORMATTED_LISTS + _THEME_LITERAL_LISTS:
                    if key not in theme:
                        continue
                    values = theme[key]
                    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                        error(f"{label}.{key} must be a non-empty array of strings (an empty one stops the region being built)")
                        continue
                    for index, text in enumerate(values):
                        leftover = set(re.findall(r"\{[^{}]*\}", text))
                        if key in _THEME_FORMATTED_LISTS:
                            leftover -= tokens
                        if leftover:
                            reason = "is never formatted" if key in _THEME_LITERAL_LISTS else "has no matching placeholders list"
                            error(f"{label}.{key}[{index}] shows {sorted(leftover)} to players as written: {key} {reason}")
                description = theme.get("description")
                if description is not None:
                    if not isinstance(description, str):
                        error(f"{label}.description must be a string")
                    elif re.search(r"\{[^{}]*\}", description):
                        error(f"{label}.description is never formatted, so its braces reach players as written")
                spawner = theme.get("spawner")
                if spawner is None:
                    continue
                if not isinstance(spawner, dict):
                    error(f"{label}.spawner must be an object")
                    continue
                for key in spawner:
                    if key not in ("monster_types", "level_range"):
                        error(f"{label}.spawner.{key} is not read (known: monster_types, level_range)")
                monsters = spawner.get("monster_types", {})
                if not isinstance(monsters, dict):
                    error(f"{label}.spawner.monster_types must be an object of NPC template -> weight")
                else:
                    for monster, weight in monsters.items():
                        if monster not in npc_ids:
                            error(f"{label}.spawner.monster_types references missing NPC template '{monster}' (the spawner skips it)")
                        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
                            error(f"{label}.spawner.monster_types.{monster} must be a positive weight")
                if "level_range" in spawner:
                    level_range = spawner["level_range"]
                    if (
                        not isinstance(level_range, list) or len(level_range) != 2
                        or any(isinstance(v, bool) or not isinstance(v, int) for v in level_range)
                        or level_range[0] < 1 or level_range[1] < level_range[0]
                    ):
                        error(f"{label}.spawner.level_range must be [min, max] positive integers")

    def theme_reference(name: Any, label: str, where: str) -> None:
        if not isinstance(name, str) or not name.strip():
            return
        if name not in themes:
            known = ", ".join(sorted(themes)) or "none -- regions/dynamic_themes.json declares no themes"
            error(f"{label} references missing theme '{name}', so no region is generated (themes: {known})", where)

    if isinstance(ruleset, dict):
        generation = ruleset.get("quest_generation")
        instance = generation.get("instance_quest") if isinstance(generation, dict) else None
        if isinstance(instance, dict):
            theme_reference(instance.get("default_procedural_theme"), "quest_generation.instance_quest.default_procedural_theme", str(ruleset_path or "ruleset"))
    quest_dir = content_root / "quests"
    for quest_path in sorted(quest_dir.glob("*.json")) if quest_dir.is_dir() else []:
        quests = _load_json(quest_path, [], "quest definitions")
        if not isinstance(quests, dict):
            continue
        for quest_id, quest in quests.items():
            if str(quest_id).startswith("_") or not isinstance(quest, dict):
                continue
            regions = quest.get("procedural_regions")
            for index, region in enumerate(regions if isinstance(regions, list) else []):
                if isinstance(region, dict):
                    theme_reference(region.get("theme"), f"quest '{quest_id}'.procedural_regions[{index}].theme", str(quest_path))


AFFIX_PREFIX_MODIFIERS = ("damage", "defense", "durability", "weight")
_AFFIX_KEYS = {
    "prefixes": ("allowed_types", "level_min", "modifiers", "equip_stats", "value_mult"),
    "suffixes": ("allowed_types", "level_min", "equip_stats", "equip_buff", "value_mult"),
}
_AFFIX_FILE_KEYS = ("prefixes", "suffixes", "generated_effect_name_pattern", "generated_description_suffix")


def _validate_affixes(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`items/affixes.json` (`items/affix_data.py`, `items/loot_generator.py`).

    `LootGenerator._pick_affix` indexes `allowed_types` directly (a missing one
    raises) and compares it with the item's engine class name, so a family name
    or a retired class never matches. `_apply_prefix` reads four `modifiers` and
    nothing else; suffixes' modifiers and prefixes' `equip_buff` are not read at
    all; `generated_effect_name_pattern` is formatted with `item_name` only.
    """
    path = content_root / "items" / "affixes.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "affixes")
    if payload is None:
        return
    source = str(path)

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", source, message))

    if not isinstance(payload, dict):
        error("affixes.json must be an object")
        return
    from engine.items.item_factory import ITEM_CLASS_MAP

    classes = {cls.__name__ for cls in ITEM_CLASS_MAP.values()}
    for key in payload:
        if not str(key).startswith("_") and key not in _AFFIX_FILE_KEYS:
            error(f"'{key}' is not read (known: {', '.join(_AFFIX_FILE_KEYS)})")
    pattern = payload.get("generated_effect_name_pattern")
    if pattern is not None:
        if not isinstance(pattern, str) or not pattern.strip():
            error("generated_effect_name_pattern must be a non-empty string")
        elif _format_placeholders(pattern) - {"item_name"}:
            error(f"generated_effect_name_pattern uses {sorted(_format_placeholders(pattern) - {'item_name'})}; only {{item_name}} is filled in, and any other raises")
    if "generated_description_suffix" in payload and not isinstance(payload["generated_description_suffix"], str):
        error("generated_description_suffix must be a string")

    for section, known in _AFFIX_KEYS.items():
        library = payload.get(section, {})
        if not isinstance(library, dict):
            error(f"{section} must be an object of affix name -> affix")
            continue
        for name, affix in library.items():
            label = f"{section}.{name}"
            if not isinstance(affix, dict):
                error(f"{label} must be an object")
                continue
            for key in affix:
                if not str(key).startswith("_") and key not in known:
                    error(f"{label}.{key} is not read for {section} (known: {', '.join(known)})")
            types = affix.get("allowed_types")
            if not isinstance(types, list) or any(not isinstance(t, str) for t in types):
                error(f"{label}.allowed_types must be an array of item classes (an absent one stops loot generation)")
            else:
                for item_type in types:
                    if item_type != "All" and item_type not in classes:
                        error(f"{label}.allowed_types '{item_type}' is not an engine item class, so it matches nothing (known: All, {', '.join(sorted(classes))})")
            level = affix.get("level_min", 1)
            if isinstance(level, bool) or not isinstance(level, int) or level < 1:
                error(f"{label}.level_min must be an integer of at least 1")
            mult = affix.get("value_mult", 1.0)
            if isinstance(mult, bool) or not isinstance(mult, (int, float)) or mult <= 0:
                error(f"{label}.value_mult must be a positive number")
            for key in ("modifiers", "equip_stats"):
                values = affix.get(key)
                if values is None:
                    continue
                if not isinstance(values, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values.values()):
                    error(f"{label}.{key} must be an object of stat -> number")
                elif key == "modifiers":
                    for stat in values:
                        if stat not in AFFIX_PREFIX_MODIFIERS:
                            error(f"{label}.modifiers.{stat} is not applied (a prefix modifies only {', '.join(AFFIX_PREFIX_MODIFIERS)}; use equip_stats for a worn stat)")
            if "equip_buff" in affix and (not isinstance(affix["equip_buff"], str) or not affix["equip_buff"].strip()):
                error(f"{label}.equip_buff must be a non-empty string")


def _validate_item_resistances_and_sets(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Item `properties.resistances` and `items/sets.json` bonuses.

    `armor_resistances` drops a value that is not a number and keys by damage
    type, so a type `combat/elements.json` does not declare protects against
    nothing. `SetManager.get_active_bonuses` runs `int()` on each threshold (a
    non-numeric one raises) and the player applies only `stat_mod` bonuses.
    """
    item_dir = content_root / "items"
    if not item_dir.is_dir():
        return
    damage_types: set[str] = set()
    elements_path = content_root / "combat" / "elements.json"
    elements = _load_json(elements_path, [], "combat vocabulary") if elements_path.is_file() else None
    if isinstance(elements, dict) and isinstance(elements.get("valid_damage_types"), list):
        damage_types = {str(value) for value in elements["valid_damage_types"]}

    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for path in sorted(item_dir.glob("*.json")):
        if path.name in ("affixes.json", "sets.json"):
            continue
        payload = _load_json(path, [], "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, item in payload.items():
            if str(item_id).startswith("_") or not isinstance(item, dict) or not isinstance(item.get("properties"), dict):
                continue
            resistances = item["properties"].get("resistances")
            if resistances is None:
                continue
            label = f"item '{item_id}'.properties.resistances"
            if not isinstance(resistances, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label} must be an object of damage type -> number"))
                continue
            for damage_type, value in resistances.items():
                if not number(value):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{damage_type} must be a number (anything else is dropped)"))
                if damage_types and damage_type not in damage_types:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{damage_type} is not a damage type combat/elements.json declares, so it resists nothing"))

    sets_path = item_dir / "sets.json"
    if not sets_path.is_file():
        return
    sets = _load_json(sets_path, issues, "item sets")
    if not isinstance(sets, dict):
        if sets is not None:
            issues.append(ContentSetIssue("error", str(sets_path), "sets.json must be an object of set id -> set"))
        return
    for set_id, item_set in sets.items():
        if str(set_id).startswith("_"):
            continue
        label = f"set '{set_id}'"
        if not isinstance(item_set, dict):
            issues.append(ContentSetIssue("error", str(sets_path), f"{label} must be an object"))
            continue
        for key in item_set:
            if not str(key).startswith("_") and key not in ("name", "items", "bonuses"):
                issues.append(ContentSetIssue("error", str(sets_path), f"{label}.{key} is not read (known: name, items, bonuses)"))
        bonuses = item_set.get("bonuses", {})
        if not isinstance(bonuses, dict):
            issues.append(ContentSetIssue("error", str(sets_path), f"{label}.bonuses must be an object of pieces-worn -> bonus"))
            continue
        for threshold, bonus in bonuses.items():
            bonus_label = f"{label}.bonuses.{threshold}"
            if not str(threshold).isdigit() or int(threshold) < 1:
                issues.append(ContentSetIssue("error", str(sets_path), f"{bonus_label}: the key must be a whole number of pieces worn (anything else raises)"))
            if not isinstance(bonus, dict) or bonus.get("type") != "stat_mod":
                issues.append(ContentSetIssue("error", str(sets_path), f"{bonus_label}.type must be 'stat_mod' (the only set bonus the player applies)"))
                continue
            modifiers = bonus.get("modifiers", {})
            if not isinstance(modifiers, dict) or any(not number(v) for v in modifiers.values()):
                issues.append(ContentSetIssue("error", str(sets_path), f"{bonus_label}.modifiers must be an object of stat -> number"))
