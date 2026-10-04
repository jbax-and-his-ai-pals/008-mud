"""Advancement sections, item-grant matchers, background stats and starting content.

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
from .abilities import (_condition_issues)
from .core import (ContentSetIssue, _load_json)
from .definitions import (_load_definition_ids)


def _validate_advancement_content(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate the authored activity-XP table.

    Two mistakes are worth catching here rather than in play, because both fail
    *silently*: a rule whose kind no engine system records pays nothing forever,
    and a rule whose kind is unrecognised is rejected outright. Either way the
    activity looks supported in the ruleset and rewards nothing in the game.
    """
    section = ruleset.get("advancement", {})
    if section is not None:
        _validate_advancement_section(section, content_root, issues, ruleset_path)

    # `AdvancementManager._config` also reads `<content_root>/advancement.json`
    # and lays the ruleset section over it one top-level key at a time, so a
    # ruleset `grants` list replaces the file's list outright rather than
    # adding to it. The file gets the same checks, and a key it loses is said.
    path = content_root / "advancement.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "advancement table")
    if payload is None:
        return
    _validate_advancement_section(payload, content_root, issues, path)
    if isinstance(payload, dict) and isinstance(section, dict):
        for key in sorted(set(payload) & set(section)):
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"'{key}' here is ignored: the ruleset's advancement.{key} replaces it entirely",
            ))


def _validate_advancement_section(section: Any, content_root: Path, issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    from engine.core.advancement import KNOWN_ENTRY_KINDS

    if not isinstance(section, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "advancement must be an object"))
        return

    curve = section.get("curve")
    if curve is not None:
        if not isinstance(curve, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.curve must be an object"))
        else:
            base = curve.get("base")
            if base is not None and (isinstance(base, bool) or not isinstance(base, (int, float)) or base <= 0):
                issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.curve.base must be a positive number"))
            multiplier = curve.get("multiplier")
            if multiplier is not None and (isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 1):
                issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.curve.multiplier must be greater than 1"))

    level_up = section.get("level_up")
    if level_up is not None:
        if not isinstance(level_up, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.level_up must be an object"))
        else:
            for key in level_up:
                if key not in ("stat_growth", "health_base"):
                    issues.append(ContentSetIssue("error", str(ruleset_path), f"advancement.level_up.{key} is not read (known: stat_growth, health_base)"))
            growth = level_up.get("stat_growth")
            if growth is not None:
                if not isinstance(growth, dict):
                    issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.level_up.stat_growth must be an object of stat name to growth per level (\"default\" is every stat not named)"))
                else:
                    for stat, amount in growth.items():
                        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
                            issues.append(ContentSetIssue("error", str(ruleset_path), f"advancement.level_up.stat_growth.{stat} must be a number of 0 or more"))
            health = level_up.get("health_base")
            if health is not None and (isinstance(health, bool) or not isinstance(health, (int, float)) or health < 0):
                issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.level_up.health_base must be a number of 0 or more: the flat health a level brings"))

    grants = section.get("grants")
    if grants is None:
        return
    if not isinstance(grants, list):
        issues.append(ContentSetIssue("error", str(ruleset_path), "advancement.grants must be an array"))
        return

    for index, grant in enumerate(grants):
        label = f"advancement.grants[{index}]"
        if not isinstance(grant, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            continue
        rule_id = str(grant.get("id", "")).strip()
        if not rule_id:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} requires an id"))
        xp = grant.get("xp", 0)
        if isinstance(xp, bool) or not isinstance(xp, (int, float)):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.xp must be a number"))
        match = grant.get("match", {})
        if not isinstance(match, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.match must be an object"))
            continue
        raw_kind = match.get("kind")
        kinds = [raw_kind] if isinstance(raw_kind, str) else (raw_kind if isinstance(raw_kind, list) else [])
        if not kinds:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.match.kind is required"))
            continue
        for kind in kinds:
            text = str(kind).strip()
            if text not in KNOWN_ENTRY_KINDS:
                issues.append(ContentSetIssue(
                    "error", str(ruleset_path),
                    f"{label}.match.kind '{text}' is not an entry kind the engine records "
                    f"(known: {', '.join(sorted(KNOWN_ENTRY_KINDS))})",
                ))

        # An item rule narrows by family (what content declared), tags, or the
        # engine's Python class name. The third is a trap: `Gem`, `Junk` and
        # `Treasure` are families whose class the engine retired, so an item built
        # from one reports `Item` and the rule can never fire. Three of
        # fantasy_frontier's five item rules were dead for exactly this reason, and
        # nothing said so -- the ledger recorded the find and paid the fallback.
        if "item" in [str(kind).strip() for kind in kinds]:
            _validate_item_grant_matchers(match, label, content_root, issues, ruleset_path)


def _validate_item_grant_matchers(
    match: dict[str, Any],
    label: str,
    content_root: Path,
    issues: list[ContentSetIssue],
    ruleset_path: Path,
) -> None:
    """Whether an item grant can ever match a real item, and say why not."""

    declared_type = str(match.get("item_type", "") or "").strip()
    if declared_type:
        from engine.items.item_factory import ITEM_CLASS_MAP

        resolved = ITEM_CLASS_MAP.get(declared_type)
        if resolved is None:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.match.item_type '{declared_type}' is not an item class the engine has "
                f"(known: {', '.join(sorted(ITEM_CLASS_MAP))})",
            ))
        elif resolved.__name__ != declared_type:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.match.item_type '{declared_type}' can never match: that class was "
                f"retired and now resolves to '{resolved.__name__}', which is what an item "
                f"reports. Match on `item_family` instead",
            ))

    declared_family = str(match.get("item_family", "") or "").strip()
    if not declared_family:
        return
    families: set[str] = set()
    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item in payload.values():
            if isinstance(item, dict) and item.get("item_family"):
                families.add(str(item["item_family"]).strip())
    if families and declared_family not in families:
        issues.append(ContentSetIssue(
            "warning", str(ruleset_path),
            f"{label}.match.item_family '{declared_family}' is declared by no item in this set, "
            f"so this grant pays nothing (families in use: {', '.join(sorted(families))})",
        ))


def _player_stat_names() -> set[str]:
    """The stat names a player really has: the scalar keys of the engine defaults.

    Read from the defaults rather than written out here, because a second list
    is a second thing to keep in step -- and the reason this check exists is
    that nothing was keeping anything in step. `resistances` is deliberately not
    a stat name: it is the container the per-channel resistances live in.
    """
    from engine.config import PLAYER_DEFAULT_STATS

    return {
        str(name) for name, value in PLAYER_DEFAULT_STATS.items()
        if not isinstance(value, dict)
    }


def _ruleset_stat_names(ruleset: dict[str, Any]) -> set[str]:
    """Stat names the content set's own ruleset names.

    A set may flavour its stats -- the sci-fi proof already does -- so a stat
    these files name is a real stat even when the engine's fantasy-flavoured
    defaults have never heard of it.
    """
    names: set[str] = set()
    skills = ruleset.get("skills") if isinstance(ruleset, dict) else None
    stat_bonuses = skills.get("stat_bonuses", {}) if isinstance(skills, dict) else {}
    if isinstance(stat_bonuses, dict):
        for rule in stat_bonuses.values():
            if isinstance(rule, dict) and isinstance(rule.get("stat"), str):
                names.add(rule["stat"].strip())
    resources = ruleset.get("resources") if isinstance(ruleset, dict) else None
    if isinstance(resources, dict):
        for field in ("max_stat", "regeneration_stat"):
            if isinstance(resources.get(field), str):
                names.add(resources[field].strip())
    return {name for name in names if name}


def _validate_background_stats(
    ruleset: dict[str, Any], stats: Any, skills: Any, label: str, path: Path,
    issues: list[ContentSetIssue],
) -> None:
    """A starting stat or skill the engine does not have is a typo, not a stat.

    `BackgroundManager` copies whatever keys it finds into `player.stats` and
    `progression.skills`. Nothing downstream ever reads `strengh`, so the typo
    is silent in both directions: it changes no number, and it reports nothing.
    Stats a set's own ruleset names are accepted alongside the engine defaults,
    because a set with a different stat vocabulary is not wrong -- a set with a
    misspelling of its own vocabulary is.
    """
    known_stats = _player_stat_names() | _ruleset_stat_names(ruleset)
    unknown = sorted(
        str(stat) for stat, value in (stats if isinstance(stats, dict) else {}).items()
        if not str(stat).startswith("_")
        and not isinstance(value, dict)
        and str(stat) not in known_stats
    )
    if unknown:
        issues.append(ContentSetIssue(
            "error",
            str(path),
            "%s.stats names %s, which is not a stat the engine or this set's ruleset "
            "declares (declared: %s)" % (
                label,
                ", ".join("'%s'" % stat for stat in unknown),
                ", ".join(sorted(known_stats)),
            ),
        ))

    skill_rules = ruleset.get("skills") if isinstance(ruleset, dict) else None
    declared_skills = skill_rules.get("stat_bonuses", {}) if isinstance(skill_rules, dict) else {}
    if not isinstance(declared_skills, dict) or not declared_skills:
        # A set that declares no stat bonuses at all is not "missing" every
        # skill -- it has opted out of stat-backed skills, which is a legitimate
        # shape for a set whose checks are not stat-driven. The warning is only
        # useful once a set has started declaring rules: then a skill granted by
        # a background but named by no rule reads as the one that was forgotten.
        return
    for skill in sorted(str(s) for s in (skills if isinstance(skills, dict) else {})):
        if skill in declared_skills:
            continue
        issues.append(ContentSetIssue(
            "warning",
            str(path),
            "%s.skills grants '%s', which ruleset skills.stat_bonuses does not name -- "
            "it will be recorded and never consulted" % (label, skill),
        ))


def _validate_starting_content(
    content_root: Path, issues: list[ContentSetIssue], ruleset: Optional[dict[str, Any]] = None
) -> None:
    """Validate backgrounds and titles -- the two P4 content files."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    recipe_path = content_root / "crafting"
    recipe_ids: set[str] = set()
    if recipe_path.is_dir():
        for path in sorted(recipe_path.glob("*.json")):
            payload = _load_json(path, issues, "crafting recipes")
            if isinstance(payload, dict):
                recipe_ids |= {str(k) for k in payload}

    backgrounds_path = content_root / "player" / "backgrounds.json"
    if backgrounds_path.is_file():
        payload = _load_json(backgrounds_path, issues, "backgrounds")
        if isinstance(payload, dict):
            for background_id, background in payload.items():
                if str(background_id).startswith("_"):
                    continue
                if not isinstance(background, dict):
                    issues.append(ContentSetIssue("error", str(backgrounds_path), f"background '{background_id}' must be an object"))
                    continue
                label = f"background '{background_id}'"
                if not str(background.get("name", "")).strip():
                    issues.append(ContentSetIssue("error", str(backgrounds_path), f"{label} requires a name"))
                equipment = background.get("equipment", {})
                if isinstance(equipment, dict):
                    for slot, item_id in equipment.items():
                        if str(item_id) not in item_ids:
                            issues.append(ContentSetIssue("error", str(backgrounds_path), f"{label}.equipment.{slot} references missing item '{item_id}'"))
                for index, entry in enumerate(background.get("inventory", []) or []):
                    if not isinstance(entry, dict) or str(entry.get("item_id", "")) not in item_ids:
                        issues.append(ContentSetIssue("error", str(backgrounds_path), f"{label}.inventory[{index}] references a missing item template"))
                for index, recipe_id in enumerate(background.get("recipes", []) or []):
                    if recipe_ids and str(recipe_id) not in recipe_ids:
                        issues.append(ContentSetIssue("error", str(backgrounds_path), f"{label}.recipes[{index}] references missing recipe '{recipe_id}'"))
                _validate_background_stats(
                    ruleset or {},
                    background.get("stats", {}),
                    background.get("skills", {}),
                    label,
                    backgrounds_path,
                    issues,
                )

    titles_path = content_root / "titles.json"
    if titles_path.is_file():
        payload = _load_json(titles_path, issues, "titles")
        if isinstance(payload, dict):
            guilds = payload.get("_guilds", {})
            if guilds is not None and not isinstance(guilds, dict):
                issues.append(ContentSetIssue("error", str(titles_path), "titles._guilds must be an object"))
                guilds = {}
            if isinstance(guilds, dict):
                region_rooms: dict[str, set[str]] = {}
                for region_path in sorted((content_root / "regions").glob("*.json")):
                    region_payload = _load_json(region_path, issues, "region")
                    if not isinstance(region_payload, dict) or isinstance(region_payload.get("themes"), dict):
                        continue
                    region_id = str(region_payload.get("region_id", "")).strip() or region_path.stem
                    rooms = region_payload.get("rooms", {})
                    if isinstance(rooms, dict):
                        region_rooms[region_id] = {str(room_id) for room_id in rooms}
                for guild_id, guild in guilds.items():
                    if not isinstance(guild, dict):
                        issues.append(ContentSetIssue("error", str(titles_path), f"titles._guilds.{guild_id} must be an object"))
                        continue
                    place = guild.get("place", "")
                    if place is None or place == "":
                        continue
                    if not isinstance(place, str) or ":" not in place:
                        issues.append(ContentSetIssue("error", str(titles_path), f"titles._guilds.{guild_id}.place must be a region_id:room_id string"))
                        continue
                    region_id, room_id = place.split(":", 1)
                    if room_id not in region_rooms.get(region_id, set()):
                        issues.append(ContentSetIssue("error", str(titles_path), f"titles._guilds.{guild_id}.place references missing room '{place}'"))
            for title_id, title in payload.items():
                if str(title_id).startswith("_"):
                    continue
                if not isinstance(title, dict):
                    issues.append(ContentSetIssue("error", str(titles_path), f"title '{title_id}' must be an object"))
                    continue
                label = f"title '{title_id}'"
                if not str(title.get("name", "")).strip():
                    issues.append(ContentSetIssue("error", str(titles_path), f"{label} requires a name"))
                issues.extend(_condition_issues(title.get("condition"), f"{label}.condition", titles_path))
                for index, requirement in enumerate(title.get("requirements", []) or []):
                    issues.extend(_condition_issues(requirement, f"{label}.requirements[{index}]", titles_path))


_CONTRACT_REGISTRY_CACHE: dict[tuple[str, int], Any] = {}
