"""Reading definition files by id, and the item-placement and teleport helpers the loader shares.

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
from .core import (ContentSetIssue, _ITEM_FIXED_KEYS, _item_field_kinds, _json_kind, _load_json)


def _item_placement_override_issues(overrides: dict, template: dict, item_ids: set[str]) -> list[tuple[str, str]]:
    """A room item placement's `properties_override`, checked against its template.

    An override replaces a value, so it keeps the value's type: the constructor
    fields have fixed types, and any other key takes the type the template's own
    property has. The item's class and family come from the template and cannot
    be changed per placement. A key the template does not have is kept as a new
    property, which only code that reads it will notice (a warning).
    """
    found: list[tuple[str, str]] = []
    properties = template.get("properties", {}) if isinstance(template.get("properties"), dict) else {}
    fields = _item_field_kinds(str(template.get("type", "Item")))
    for key, value in overrides.items():
        if str(key).startswith("_"):
            continue
        if key in _ITEM_FIXED_KEYS:
            found.append(("error", f"{key} cannot be changed by a placement (the template decides what the item is)"))
            continue
        expected = fields.get(key)
        if expected is None and key in properties and properties[key] is not None:
            expected = _json_kind(properties[key])
        if expected is None:
            if key not in properties and key not in fields:
                found.append(("warning", f"{key} is not a property of this item's template; it is kept, but only code that reads '{key}' will notice"))
            continue
        if _json_kind(value) != expected:
            found.append(("error", f"{key} must be a {expected} (got {_json_kind(value)}); an override keeps the type of the value it replaces"))
            continue
        if expected == "number" and value < 0:
            found.append(("error", f"{key} must not be negative"))
        if key in ("name",) and not value.strip():
            found.append(("error", "name must not be empty"))
        if key == "key_id" and value and value not in item_ids:
            found.append(("error", f"key_id references missing item '{value}'"))
        if expected == "array" and key in ("contents", "contains"):
            for entry in value:
                target = entry.get("item_id") if isinstance(entry, dict) else None
                if target not in item_ids:
                    found.append(("error", f"{key} references missing item {target!r}"))
    return found


def _teleport_destinations(content_root: Path) -> list[tuple[str, str]]:
    """Every `(region, room)` a `teleport` effect anywhere in the set's authored effects names."""
    found: list[tuple[str, str]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("teleport", "set_respawn"):   # a place the player can rise again is a place they can be
                target = value.get(key)
                if isinstance(target, dict) and isinstance(target.get("region"), str) and isinstance(target.get("room"), str):
                    found.append((target["region"], target["room"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for folder in ("triggers", "scenes", "dialogue", "campaigns", "quests", "knowledge"):
        directory = content_root / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                walk(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return found


def _load_definition_ids(directory: Path, label: str, issues: list[ContentSetIssue]) -> set[str]:
    """Read template ids from a content directory without constructing a world."""
    definition_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, label)
        if not isinstance(payload, dict):
            continue
        for definition_id, definition in payload.items():
            if isinstance(definition, dict) and not str(definition_id).startswith("_"):
                definition_ids.add(str(definition_id))
    return definition_ids
