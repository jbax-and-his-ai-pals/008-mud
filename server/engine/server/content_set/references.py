"""Ruleset references to the set's own content (quest board rooms and the like).

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
from .weather_skills import (_QUEST_TEXT_TEMPLATE_FIELDS, _QUEST_TEXT_TEMPLATE_TYPES)


def _format_placeholders(text: str) -> set[str]:
    """Field names a `str.format` call would need to fill in `text`."""
    return {
        field_name for _, field_name, _, _ in string.Formatter().parse(text)
        if field_name
    }


def _quest_board_room_refs(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    room_refs: set[str] = set()
    region_dir = content_root / "regions"
    for path in sorted(region_dir.glob("*.json")):
        region = _load_json(path, issues, "region definitions")
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id", path.stem)).strip()
        rooms = region.get("rooms", {})
        if not region_id or not isinstance(rooms, dict):
            continue
        for room_id in rooms:
            if isinstance(room_id, str) and room_id.strip():
                room_refs.add(f"{region_id}:{room_id}")
    return room_refs


def _validate_ruleset_references(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate optional cross-file references made by generic ruleset systems."""
    quest_generation = ruleset.get("quest_generation", {})
    if not isinstance(quest_generation, dict):
        return
    source = str(ruleset_path)
    quest_ids = _load_definition_ids(content_root / "quests", "quest definitions", issues)
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)

    configured = quest_generation.get("authored_board_templates", [])
    if configured is not None and not isinstance(configured, list):
        issues.append(ContentSetIssue("error", source, "quest_generation.authored_board_templates must be an array"))
    elif isinstance(configured, list):
        for index, entry in enumerate(configured):
            label = f"quest_generation.authored_board_templates[{index}]"
            if not isinstance(entry, dict):
                issues.append(ContentSetIssue("error", source, f"{label} must be an object"))
                continue
            template_id = entry.get("template_id")
            if not isinstance(template_id, str) or not template_id.strip():
                issues.append(ContentSetIssue("error", source, f"{label}.template_id must be a non-empty string"))
            elif template_id not in quest_ids:
                issues.append(ContentSetIssue("error", source, f"{label} references missing quest template '{template_id}'"))
            giver_template_id = entry.get("giver_template_id")
            if giver_template_id is not None and (not isinstance(giver_template_id, str) or not giver_template_id.strip()):
                issues.append(ContentSetIssue("error", source, f"{label}.giver_template_id must be a non-empty string when provided"))
            elif isinstance(giver_template_id, str) and giver_template_id not in npc_ids:
                issues.append(ContentSetIssue("error", source, f"{label} references missing NPC template '{giver_template_id}'"))
            if "relationship_min" in entry:
                relationship_min = entry["relationship_min"]
                if isinstance(relationship_min, bool) or not isinstance(relationship_min, int) or relationship_min < 0 or relationship_min > 100:
                    issues.append(ContentSetIssue("error", source, f"{label}.relationship_min must be an integer from 0 to 100"))
            if "repeatable" in entry:
                repeatable = entry["repeatable"]
                if not isinstance(repeatable, dict):
                    issues.append(ContentSetIssue("error", source, f"{label}.repeatable must be an object"))
                    continue
                delay_seconds = repeatable.get("delay_seconds")
                if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or delay_seconds <= 0:
                    issues.append(ContentSetIssue("error", source, f"{label}.repeatable.delay_seconds must be a positive number"))
                unavailable_text = repeatable.get("unavailable_text")
                if not isinstance(unavailable_text, str) or not unavailable_text.strip():
                    issues.append(ContentSetIssue("error", source, f"{label}.repeatable.unavailable_text must be a non-empty string"))

    if "quest_board_locations" in quest_generation:
        locations = quest_generation["quest_board_locations"]
        if not isinstance(locations, list) or not locations:
            issues.append(ContentSetIssue("error", source, "quest_generation.quest_board_locations must be a non-empty array"))
        else:
            room_refs = _quest_board_room_refs(content_root, issues)
            for index, location in enumerate(locations):
                label = f"quest_generation.quest_board_locations[{index}]"
                if not isinstance(location, str) or ":" not in location:
                    issues.append(ContentSetIssue("error", source, f"{label} must be a 'region_id:room_id' string"))
                elif location not in room_refs:
                    issues.append(ContentSetIssue("error", source, f"{label} references missing room '{location}'"))

    if "delivery_package_item_id" in quest_generation:
        delivery_item = quest_generation["delivery_package_item_id"]
        if not isinstance(delivery_item, str) or not delivery_item.strip():
            issues.append(ContentSetIssue("error", source, "quest_generation.delivery_package_item_id must be a non-empty string"))
        elif delivery_item not in item_ids:
            issues.append(ContentSetIssue("error", source, f"quest_generation.delivery_package_item_id references missing item template '{delivery_item}'"))

    if "board_display_name" in quest_generation:
        board_display_name = quest_generation["board_display_name"]
        if not isinstance(board_display_name, str) or not board_display_name.strip():
            issues.append(ContentSetIssue("error", source, "quest_generation.board_display_name must be a non-empty string"))

    if "turn_in_phrases" in quest_generation:
        turn_in_phrases = quest_generation["turn_in_phrases"]
        if not isinstance(turn_in_phrases, list) or not turn_in_phrases or any(
            not isinstance(phrase, str) or not phrase.strip() for phrase in turn_in_phrases
        ):
            issues.append(ContentSetIssue("error", source, "quest_generation.turn_in_phrases must be a non-empty array of non-empty strings"))

    if "npc_quest_interests" in quest_generation:
        interests = quest_generation["npc_quest_interests"]
        if not isinstance(interests, dict):
            issues.append(ContentSetIssue("error", source, "quest_generation.npc_quest_interests must be an object"))
        else:
            for template_id, tags in interests.items():
                label = f"quest_generation.npc_quest_interests.{template_id}"
                if not isinstance(template_id, str) or template_id not in npc_ids:
                    issues.append(ContentSetIssue("error", source, f"{label} references missing NPC template '{template_id}'"))
                if not isinstance(tags, list) or not tags or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
                    issues.append(ContentSetIssue("error", source, f"{label} must be a non-empty array of non-empty strings"))

    if "procedural_naming" in quest_generation:
        procedural_naming = quest_generation["procedural_naming"]
        if not isinstance(procedural_naming, dict):
            issues.append(ContentSetIssue("error", source, "quest_generation.procedural_naming must be an object"))
        else:
            for field in ("adjectives", "nouns"):
                if field in procedural_naming:
                    values = procedural_naming[field]
                    if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                        issues.append(ContentSetIssue("error", source, f"quest_generation.procedural_naming.{field} must be an array of non-empty strings"))
            name_pattern = procedural_naming.get("default_name_pattern")
            if name_pattern is not None:
                if not isinstance(name_pattern, str) or not name_pattern.strip():
                    issues.append(ContentSetIssue("error", source, "quest_generation.procedural_naming.default_name_pattern must be a non-empty string"))
                else:
                    extra = _format_placeholders(name_pattern) - {"Adjective", "Noun"}
                    if extra:
                        issues.append(ContentSetIssue(
                            "error", source,
                            f"quest_generation.procedural_naming.default_name_pattern uses unknown placeholder(s) {sorted(extra)}; "
                            "only {Adjective} and {Noun} are filled in",
                        ))
            base_template_id = procedural_naming.get("default_base_template_id")
            if base_template_id is not None and base_template_id != "":
                if not isinstance(base_template_id, str):
                    issues.append(ContentSetIssue("error", source, "quest_generation.procedural_naming.default_base_template_id must be a string"))
                elif base_template_id not in item_ids:
                    issues.append(ContentSetIssue("error", source, f"quest_generation.procedural_naming.default_base_template_id references missing item template '{base_template_id}'"))

    if "instance_quest" in quest_generation:
        instance_quest = quest_generation["instance_quest"]
        if not isinstance(instance_quest, dict):
            issues.append(ContentSetIssue("error", source, "quest_generation.instance_quest must be an object"))
        else:
            for field in ("entry_exit_command", "entry_description_when_visible", "default_procedural_theme"):
                if field in instance_quest and not isinstance(instance_quest[field], str):
                    issues.append(ContentSetIssue("error", source, f"quest_generation.instance_quest.{field} must be a string"))
            # `generate_instance_quest` formats these with only `creature_name` and
            # no try/except, unlike every other quest text pattern -- an unknown
            # placeholder here is a live crash, not a silent fallback.
            for field in ("title_pattern", "description_pattern"):
                pattern = instance_quest.get(field)
                if pattern is None:
                    continue
                if not isinstance(pattern, str) or not pattern.strip():
                    issues.append(ContentSetIssue("error", source, f"quest_generation.instance_quest.{field} must be a non-empty string"))
                    continue
                extra = _format_placeholders(pattern) - {"creature_name"}
                if extra:
                    issues.append(ContentSetIssue(
                        "error", source,
                        f"quest_generation.instance_quest.{field} uses unknown placeholder(s) {sorted(extra)}; "
                        "only {creature_name} is filled in, and an unknown one crashes quest generation",
                    ))

    if "text_templates" in quest_generation:
        text_templates = quest_generation["text_templates"]
        if not isinstance(text_templates, dict):
            issues.append(ContentSetIssue("error", source, "quest_generation.text_templates must be an object"))
        else:
            for quest_type, template in text_templates.items():
                label = f"quest_generation.text_templates.{quest_type}"
                if quest_type not in _QUEST_TEXT_TEMPLATE_TYPES:
                    issues.append(ContentSetIssue(
                        "error", source,
                        f"{label} is not a generated quest type (expected one of {list(_QUEST_TEXT_TEMPLATE_TYPES)})",
                    ))
                if not isinstance(template, dict):
                    issues.append(ContentSetIssue("error", source, f"{label} must be an object"))
                    continue
                for text_field in ("title", "description"):
                    text = template.get(text_field)
                    if not isinstance(text, str) or not text.strip():
                        issues.append(ContentSetIssue("error", source, f"{label}.{text_field} must be a non-empty string"))
                        continue
                    extra = _format_placeholders(text) - set(_QUEST_TEXT_TEMPLATE_FIELDS)
                    if extra:
                        issues.append(ContentSetIssue(
                            "error", source,
                            f"{label}.{text_field} uses unknown placeholder(s) {sorted(extra)}; "
                            f"a missing one silently falls back to \"Task\" instead of crashing",
                        ))
