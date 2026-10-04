"""Feature profiles and loot settings, ambient loot, collections and discoveries.

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
from .core import (ContentSetIssue, _load_definitions, _load_json)
from .definitions import (_load_definition_ids)
from .references import (_format_placeholders)


def _validate_feature_profile(profile: dict[str, Any], path: Path, issues: list[ContentSetIssue], campaign_ids: set[str]) -> None:
    """A feature profile's modes and policies (`feature_profile.py`; the
    policy readers in `headless/party.py`, `shard.py`, `finite_adventure.py`).

    An unknown mode was a boot warning and the default; a misspelled category
    or key, a policy value its reader does not act on, or a non-boolean switch
    was read as the default with no word at all. `_` keys are notes.
    """
    from engine.server.feature_profile import (
        _ALLOWED_MODES, POLICY_ALIASES, POLICY_SYNONYMS, PROFILE_POLICIES, PROVIDER_CATEGORIES,
    )

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(path), message))

    modes = {mode_path.split(".")[0]: values for mode_path, values in _ALLOWED_MODES.items()}
    for category, node in profile.items():
        if str(category).startswith("_"):
            continue
        policy_name = POLICY_ALIASES.get(category, category)
        if category not in modes and policy_name not in PROFILE_POLICIES:
            known = sorted(set(modes) | set(PROFILE_POLICIES) | set(POLICY_ALIASES))
            error(f"'{category}' is not a feature profile section the server reads ({', '.join(known)})")
            continue
        if not isinstance(node, dict):
            error(f"{category} must be an object")
            continue
        if category in modes:
            for key, value in node.items():
                if str(key).startswith("_"):
                    continue
                if key == "mode":
                    if str(value).strip().lower() not in modes[category]:
                        error(f"{category}.mode '{value}' is not one of {sorted(v for v in modes[category] if v)} (the server would use its default)")
                elif key == "provider_id" and category in PROVIDER_CATEGORIES:
                    if not isinstance(value, str) or not value.strip():
                        error(f"{category}.provider_id must be a non-empty string")
                    elif str(node.get("mode", "")).strip().lower() != "custom":
                        error(f"{category}.provider_id is read only when {category}.mode is 'custom'")
                else:
                    error(f"{category}.{key} is not read by the server")
            continue
        for key, value in node.items():
            if str(key).startswith("_"):
                continue
            kind = PROFILE_POLICIES[policy_name].get(key)
            label = f"{category}.{key}"
            if kind is None:
                error(f"{label} is not read by the server ({', '.join(sorted(PROFILE_POLICIES[policy_name]))})")
            elif isinstance(kind, list):
                word = str(value).strip().lower() if isinstance(value, str) else None
                word = POLICY_SYNONYMS.get(key, {}).get(word, word)
                if word not in kind:
                    error(f"{label} '{value}' is not one of {kind}")
            elif kind == "bool" and not isinstance(value, bool):
                error(f"{label} must be true or false")
            elif kind == "seconds" and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                error(f"{label} must be a number of seconds, 0 or more")
            elif kind == "text" and not isinstance(value, str):
                error(f"{label} must be a string")
            elif kind == "campaign" and (not isinstance(value, str) or (value.strip() and value.strip() not in campaign_ids)):
                error(f"{label} '{value}' is not a campaign in this set")


LOOT_KEYS = ("take_hint", "chest_materials", "currency_item_id", "ambient_pools")


def _validate_loot_settings(content_root: Path, loot: dict, issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """`loot.take_hint`, `chest_materials` and `currency_item_id`.

    Each falls back without a word (utils.py `_loot_take_hint`,
    chest_loot_generator.py): a chest material that is not an item template is
    dropped, and with none left any Container is used; a currency id that is not
    an item is replaced by whichever item is typed as coin; a hint whose
    placeholder is not `{items}` or `{count}` becomes the engine's default.
    """
    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(ruleset_path), message))

    for key in loot:
        if not str(key).startswith("_") and key not in LOOT_KEYS:
            error(f"loot.{key} is not read (known: {', '.join(LOOT_KEYS)})")
    items = _load_definitions(content_root / "items")
    if "take_hint" in loot:
        hint = loot["take_hint"]
        if hint is not False and not isinstance(hint, str):
            error("loot.take_hint must be text, or false for no hint")
        elif isinstance(hint, str):
            try:
                unknown = sorted(_format_placeholders(hint) - {"items", "count"})
            except ValueError as problem:
                error(f"loot.take_hint is not a valid message template ({problem})")
            else:
                if unknown:
                    error(f"loot.take_hint uses {', '.join('{' + name + '}' for name in unknown)}; only {{items}} and {{count}} are filled, so the default hint is shown instead")
    if "chest_materials" in loot:
        materials = loot["chest_materials"]
        if not isinstance(materials, list) or not materials:
            error("loot.chest_materials must be a non-empty array of chest item ids, plainest first")
        else:
            for index, item_id in enumerate(materials):
                template = items.get(item_id) if isinstance(item_id, str) else None
                if template is None:
                    error(f"loot.chest_materials[{index}] references missing item {item_id!r} (it is dropped from the list)")
                elif template.get("type") != "Container":
                    error(f"loot.chest_materials[{index}] '{item_id}' is not a Container, so it cannot hold loot")
    if "currency_item_id" in loot:
        currency = loot["currency_item_id"]
        if not isinstance(currency, str) or currency not in items:
            error(f"loot.currency_item_id references missing item {currency!r} (a coin-typed item is used instead)")


def _validate_ambient_loot_references(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate generic, content-authored ambient loot pools."""
    loot = ruleset.get("loot", {})
    if loot is None:
        return
    if not isinstance(loot, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "loot must be an object"))
        return
    _validate_loot_settings(content_root, loot, issues, ruleset_path)
    pools = loot.get("ambient_pools", [])
    if pools is None:
        return
    if not isinstance(pools, list):
        issues.append(ContentSetIssue("error", str(ruleset_path), "loot.ambient_pools must be an array"))
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for index, pool in enumerate(pools):
        label = f"loot.ambient_pools[{index}]"
        if not isinstance(pool, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            continue
        chance = pool.get("chance")
        if isinstance(chance, bool) or not isinstance(chance, (int, float)) or chance < 0 or chance > 1:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.chance must be a number from 0 to 1"))
        for selector in ("npc_template_ids", "npc_tags_any", "npc_tags_all", "npc_tags_none"):
            if selector in pool and (
                not isinstance(pool[selector], list)
                or any(not isinstance(value, str) or not value.strip() for value in pool[selector])
            ):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.{selector} must be an array of non-empty strings"))
        entries = pool.get("entries")
        if not isinstance(entries, list) or not entries:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.entries must be a non-empty array"))
            continue
        for entry_index, entry in enumerate(entries):
            entry_label = f"{label}.entries[{entry_index}]"
            if not isinstance(entry, dict):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{entry_label} must be an object"))
                continue
            item_id = entry.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip() or item_id not in item_ids:
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{entry_label} references missing item template '{item_id}'"))
            if "weight" in entry and (isinstance(entry["weight"], bool) or not isinstance(entry["weight"], (int, float)) or entry["weight"] <= 0):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{entry_label}.weight must be a positive number"))


def _validate_collection_references(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate optional data-authored collection definitions.

    Collections deliberately remain a generic item-list/reward contract.  The
    validator only checks that authored lists are usable by the engine and
    that their item references survive content-set loading.
    """
    collections_path = content_root / "collections.json"
    if not collections_path.exists():
        return
    payload = _load_json(collections_path, issues, "collections")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(collections_path), "collections must be an object"))
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for collection_id, definition in payload.items():
        if str(collection_id).startswith("_"):
            continue
        label = f"collection '{collection_id}'"
        if not isinstance(collection_id, str) or not collection_id.strip():
            issues.append(ContentSetIssue("error", str(collections_path), "collection ids must be non-empty strings"))
            continue
        if not isinstance(definition, dict):
            issues.append(ContentSetIssue("error", str(collections_path), f"{label} must be an object"))
            continue
        items = definition.get("items")
        if not isinstance(items, list) or not items or any(not isinstance(item_id, str) or not item_id.strip() for item_id in items):
            issues.append(ContentSetIssue("error", str(collections_path), f"{label}.items must be a non-empty array of item ids"))
            continue
        if len(set(items)) != len(items):
            issues.append(ContentSetIssue("error", str(collections_path), f"{label}.items must not contain duplicates"))
        for item_id in items:
            if item_id not in item_ids:
                issues.append(ContentSetIssue("error", str(collections_path), f"{label} references missing item template '{item_id}'"))
        rewards = definition.get("rewards", {})
        if not isinstance(rewards, dict):
            issues.append(ContentSetIssue("error", str(collections_path), f"{label}.rewards must be an object"))


def _validate_discovery_references(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate portable discovery journal records and their item triggers."""
    path = content_root / "discoveries.json"
    if not path.exists():
        return
    payload = _load_json(path, issues, "discoveries")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(path), "discoveries must be an object"))
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for discovery_id, definition in payload.items():
        if str(discovery_id).startswith("_"):
            continue
        label = f"discovery '{discovery_id}'"
        if not isinstance(discovery_id, str) or not discovery_id.strip() or not isinstance(definition, dict):
            issues.append(ContentSetIssue("error", str(path), f"{label} must have a non-empty id and object definition"))
            continue
        if not isinstance(definition.get("name"), str) or not definition["name"].strip():
            issues.append(ContentSetIssue("error", str(path), f"{label}.name must be a non-empty string"))
        item_triggers = definition.get("item_ids", [])
        tag_triggers = definition.get("item_tags", [])
        if not isinstance(item_triggers, list) or not isinstance(tag_triggers, list):
            issues.append(ContentSetIssue("error", str(path), f"{label}.item_ids and item_tags must be arrays"))
            continue
        if not item_triggers and not tag_triggers:
            issues.append(ContentSetIssue("error", str(path), f"{label} requires at least one item_ids or item_tags trigger"))
        if any(not isinstance(item_id, str) or not item_id.strip() for item_id in item_triggers):
            issues.append(ContentSetIssue("error", str(path), f"{label}.item_ids must contain non-empty item ids"))
        if len(set(item_triggers)) != len(item_triggers):
            issues.append(ContentSetIssue("error", str(path), f"{label}.item_ids must not contain duplicates"))
        for item_id in item_triggers:
            if item_id not in item_ids:
                issues.append(ContentSetIssue("error", str(path), f"{label} references missing item template '{item_id}'"))
        if any(not isinstance(tag, str) or not tag.strip() for tag in tag_triggers):
            issues.append(ContentSetIssue("error", str(path), f"{label}.item_tags must contain non-empty tags"))
