"""Region policy: level bands, hazard coverage, classification, districts, spawners.

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


def _region_level_bands_required(
    ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path
) -> bool:
    """Read the optional content-set policy that requires region bands.

    Level bands are a world-design commitment for a level-based set, not a
    universal runtime requirement: a modern social capsule or a set without
    progression should be free to omit them. Opting in makes every static
    region carry the same explicit, portable progression metadata.
    """
    world_config = ruleset.get("world", {})
    if world_config is None:
        return False
    if not isinstance(world_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world must be an object"))
        return False
    regions_config = world_config.get("regions", {})
    if regions_config is None:
        return False
    if not isinstance(regions_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions must be an object"))
        return False
    required = regions_config.get("require_level_bands", False)
    if not isinstance(required, bool):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions.require_level_bands must be a boolean"))
        return False
    return required


def _region_hazard_coverage_required(
    ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path
) -> bool:
    """Read the optional policy that requires every authored hazard in play.

    A set can define hazards without making all of them part of its world. A
    set built around environmental danger can opt into this check, which
    derives the required names from its own combat content rather than from an
    engine-maintained list.
    """
    world_config = ruleset.get("world", {})
    if world_config is None:
        return False
    if not isinstance(world_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world must be an object"))
        return False
    regions_config = world_config.get("regions", {})
    if regions_config is None:
        return False
    if not isinstance(regions_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions must be an object"))
        return False
    required = regions_config.get("require_hazard_coverage", False)
    if not isinstance(required, bool):
        issues.append(ContentSetIssue(
            "error", str(ruleset_path),
            "ruleset.world.regions.require_hazard_coverage must be a boolean",
        ))
        return False
    return required


def _region_classification_policy(
    ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path
) -> tuple[bool, set[str], set[str]]:
    """Read an optional, content-owned vocabulary for static region metadata.

    ``biome`` and ``region_type`` intentionally remain ordinary region
    properties at runtime. A content set can opt into a controlled vocabulary
    without imposing a fantasy taxonomy on every content set.
    """
    world_config = ruleset.get("world", {})
    if world_config is None:
        return False, set(), set()
    if not isinstance(world_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world must be an object"))
        return False, set(), set()
    regions_config = world_config.get("regions", {})
    if regions_config is None:
        return False, set(), set()
    if not isinstance(regions_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions must be an object"))
        return False, set(), set()
    required = regions_config.get("require_classification", False)
    if not isinstance(required, bool):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions.require_classification must be a boolean"))
        return False, set(), set()

    def vocabulary(key: str) -> set[str]:
        values = regions_config.get(key, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"ruleset.world.regions.{key} must be a list of non-empty strings"))
            return set()
        return {value.strip() for value in values}

    biomes = vocabulary("biomes")
    region_types = vocabulary("region_types")
    if required and (not biomes or not region_types):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions requires non-empty biomes and region_types when classification is required"))
    return required, biomes, region_types


def _validate_district_coverage_policy(
    ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path
) -> None:
    """Type-check the optional policy that guarantees every room in every
    region resolves to *some* district at runtime.

    Unlike `require_level_bands`/`require_classification`/
    `require_hazard_coverage`, this one asks nothing of the author: opting in
    makes `world.get_district` (engine/world/world.py) synthesize a hidden
    catch-all district for whatever a room's author left ungrouped, so there
    is no per-region shape to check here beyond the flag's own type.
    """
    world_config = ruleset.get("world", {})
    if world_config is None:
        return
    if not isinstance(world_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world must be an object"))
        return
    regions_config = world_config.get("regions", {})
    if regions_config is None:
        return
    if not isinstance(regions_config, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.world.regions must be an object"))
        return
    enforced = regions_config.get("enforce_district_coverage", False)
    if not isinstance(enforced, bool):
        issues.append(ContentSetIssue(
            "error", str(ruleset_path),
            "ruleset.world.regions.enforce_district_coverage must be a boolean",
        ))


def _validate_region_classification(
    content_root: Path, issues: list[ContentSetIssue], *, required: bool = False,
    biomes: set[str] | None = None, region_types: set[str] | None = None,
) -> None:
    """Validate optional content-owned ``biome`` and ``region_type`` labels."""
    biomes = biomes or set()
    region_types = region_types or set()
    for path in sorted((content_root / "regions").glob("*.json")):
        payload = _load_json(path, issues, "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        region_id = str(payload.get("region_id", "")).strip() or path.stem
        properties = payload.get("properties", {})
        if not isinstance(properties, dict):
            if required:
                issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' properties must be an object containing biome and region_type"))
            continue
        for key, vocabulary in (("biome", biomes), ("region_type", region_types)):
            value = properties.get(key)
            if value is None:
                if required:
                    issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' requires properties.{key}"))
            elif not isinstance(value, str) or not value.strip():
                issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' properties.{key} must be a non-empty string"))
            elif vocabulary and value not in vocabulary:
                issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' properties.{key} '{value}' is not in the ruleset vocabulary"))


_REGION_SPAWNER_KEYS = ("monster_types", "npc_types", "level_range", "monsters_enabled", "npcs_enabled")


def _validate_region_spawners(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A region's `spawner` (`world/spawner.py`), beyond its `level_range`.

    `weighted_choice` picks a template id and the spawner then skips one with
    no template, so a misspelt creature simply never appears; a misspelt key or
    toggle is never read.
    """
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    for path in sorted(region_dir.glob("*.json")):
        payload = _load_json(path, [], "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        spawner = payload.get("spawner")
        if spawner is None:
            continue
        region_id = str(payload.get("region_id", "")).strip() or path.stem
        label = f"region '{region_id}' spawner"
        if not isinstance(spawner, dict):
            issues.append(ContentSetIssue("error", str(path), f"{label} must be an object"))
            continue
        for key in spawner:
            if not str(key).startswith("_") and key not in _REGION_SPAWNER_KEYS:
                issues.append(ContentSetIssue("error", str(path), f"{label}.{key} is not read (known: {', '.join(_REGION_SPAWNER_KEYS)})"))
        for key in ("monsters_enabled", "npcs_enabled"):
            if key in spawner and not isinstance(spawner[key], bool):
                issues.append(ContentSetIssue("error", str(path), f"{label}.{key} must be true or false"))
        for key in ("monster_types", "npc_types"):
            weights = spawner.get(key)
            if weights is None:
                continue
            if not isinstance(weights, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.{key} must be an object of NPC template -> weight"))
                continue
            for template_id, weight in weights.items():
                if template_id not in npc_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{key} references missing NPC template '{template_id}' (it never spawns)"))
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{key}.{template_id} must be a positive weight"))


def _validate_region_level_bands(
    content_root: Path, issues: list[ContentSetIssue], *, required: bool = False
) -> None:
    """Validate portable authored progression bands and their spawn alignment."""
    for path in sorted((content_root / "regions").glob("*.json")):
        payload = _load_json(path, issues, "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        region_id = str(payload.get("region_id", "")).strip() or path.stem
        properties = payload.get("properties", {})
        if not isinstance(properties, dict):
            if required:
                issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' properties must be an object containing level_band"))
            continue
        band = properties.get("level_band")
        if band is None:
            if required:
                issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' requires properties.level_band"))
            continue
        if not isinstance(band, dict):
            issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' properties.level_band must be an object"))
            continue
        minimum = band.get("min")
        maximum = band.get("max")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 1
            or maximum < minimum
        ):
            issues.append(ContentSetIssue(
                "error", str(path),
                f"region '{region_id}' properties.level_band requires positive integer min/max with min <= max",
            ))
            continue
        spawner = payload.get("spawner", {})
        level_range = spawner.get("level_range") if isinstance(spawner, dict) else None
        if level_range is None:
            continue
        if (
            not isinstance(level_range, list)
            or len(level_range) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in level_range)
            or level_range[0] < 1
            or level_range[1] < level_range[0]
        ):
            issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' spawner.level_range must be [min, max] positive integers"))
        elif level_range[0] < minimum or level_range[1] > maximum:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"region '{region_id}' spawner.level_range must stay inside properties.level_band",
            ))


def _validate_region_hazard_coverage(
    content_root: Path, issues: list[ContentSetIssue], *, required: bool = False
) -> None:
    """Validate room hazards against the set's own declarations and coverage.

    A hazard is one record in `combat/elements.json` -- channel, prose, base
    damage, tick interval -- and a room names it. Only a ruleset that opts in has
    to place every declared hazard; whenever an elements file exists, individual
    room hazards are still checked for valid names and safe numeric values.
    """
    elements_path = content_root / "combat" / "elements.json"
    if not elements_path.is_file():
        if required:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                "hazard coverage requires data/combat/elements.json declaring hazards",
            ))
        return

    elements_payload = _load_json(elements_path, issues, "combat elements")
    if not isinstance(elements_payload, dict):
        return
    declared_hazards = elements_payload.get("hazards")
    if not isinstance(declared_hazards, dict):
        if required:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                "hazard coverage requires hazards to be an object of hazard records",
            ))
        return

    # The old shape, named explicitly. Its two keys would otherwise be read as two
    # hazards whose records are missing everything, and the author would get four
    # confusing errors instead of one sentence about what changed.
    for retired in ("mapping", "flavor"):
        if retired in declared_hazards:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                f"hazards.{retired} is the retired shape: each hazard is now one record "
                f"with its own `channel`, `flavor`, `damage` and `tick_interval`, keyed by "
                f"the id a room names",
            ))

    valid_damage_types = {
        str(entry).strip() for entry in elements_payload.get("valid_damage_types", [])
        if isinstance(entry, str) and entry.strip()
    }
    valid_hazards: set[str] = set()
    for hazard_id, record in declared_hazards.items():
        if hazard_id in ("mapping", "flavor"):
            continue
        label = f"hazards.{hazard_id}"
        if not isinstance(hazard_id, str) or not hazard_id.strip():
            issues.append(ContentSetIssue(
                "error", str(elements_path), "hazard ids must be non-empty strings",
            ))
            continue
        if not isinstance(record, dict):
            issues.append(ContentSetIssue(
                "error", str(elements_path), f"{label} must be an object",
            ))
            continue
        valid_hazards.add(hazard_id.strip())

        channel = record.get("channel")
        if not isinstance(channel, str) or not channel.strip():
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                f"{label}.channel must name the damage channel this hazard deals through",
            ))
        elif valid_damage_types and channel.strip() not in valid_damage_types:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                f"{label}.channel '{channel.strip()}' is not one of this set's damage types "
                f"({', '.join(sorted(valid_damage_types))})",
            ))
        flavor = record.get("flavor")
        if not isinstance(flavor, str) or not flavor.strip():
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                f"{label}.flavor must say what a player reads when it hurts them: content's "
                f"words, because the engine's own sentence is the leak hazards are worst at",
            ))
        for field in ("damage", "tick_interval"):
            if field not in record:
                continue
            value = record.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                issues.append(ContentSetIssue(
                    "error", str(elements_path), f"{label}.{field} must be a positive number",
                ))

    if required and not valid_hazards:
        issues.append(ContentSetIssue(
            "error", str(elements_path), "hazard coverage requires at least one declared hazard",
        ))

    authored_locations: dict[str, list[str]] = {}
    for path in sorted((content_root / "regions").glob("*.json")):
        payload = _load_json(path, issues, "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        region_id = str(payload.get("region_id", "")).strip() or path.stem
        rooms = payload.get("rooms")
        if not isinstance(rooms, dict):
            continue
        for room_id, room in rooms.items():
            if not isinstance(room, dict):
                continue
            properties = room.get("properties", {})
            if not isinstance(properties, dict) or ("hazard_type" not in properties and "hazards" not in properties):
                continue
            room_label = f"room '{region_id}:{room_id}'"
            # A room names several hazards as `hazards: [{type, damage?,
            # tick_interval?, weather_multipliers?}]`, or one with the flat keys.
            # Both at once would leave the flat ones silently unread.
            if "hazards" in properties:
                if any(key in properties for key in ("hazard_type", "hazard_damage", "hazard_tick_interval", "weather_hazard_multipliers")):
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{room_label} names hazards both ways: move hazard_type and its numbers into the hazards list",
                    ))
                listed = properties.get("hazards")
                if not isinstance(listed, list):
                    issues.append(ContentSetIssue("error", str(path), f"{room_label} hazards must be a list of hazard entries"))
                    continue
                entries = [(f"{room_label} hazards[{index}]", entry) for index, entry in enumerate(listed)]
            else:
                entries = [(room_label, {
                    "type": properties.get("hazard_type"),
                    "damage": properties.get("hazard_damage"),
                    "tick_interval": properties.get("hazard_tick_interval"),
                    "weather_multipliers": properties.get("weather_hazard_multipliers"),
                })]
            flat = "hazards" not in properties
            seen_in_room: set[str] = set()
            for entry_label, entry in entries:
                if not isinstance(entry, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                    continue
                type_key = "hazard_type" if flat else "type"
                hazard_type = entry.get("type")
                if not isinstance(hazard_type, str) or not hazard_type.strip():
                    issues.append(ContentSetIssue(
                        "error", str(path), f"{entry_label} {type_key} must be a non-empty string",
                    ))
                    continue
                hazard_type = hazard_type.strip()
                if hazard_type not in valid_hazards:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{entry_label} uses unknown {type_key} '{hazard_type}': no hazard of that "
                        f"name is declared in {elements_path.name}",
                    ))
                    continue
                if hazard_type in seen_in_room:
                    issues.append(ContentSetIssue(
                        "error", str(path), f"{entry_label} names '{hazard_type}' a second time in the same room",
                    ))
                seen_in_room.add(hazard_type)
                authored_locations.setdefault(hazard_type, []).append(f"{region_id}:{room_id}")
                if not flat:
                    for key in entry:
                        if key not in ("type", "damage", "tick_interval", "weather_multipliers"):
                            issues.append(ContentSetIssue(
                                "error", str(path),
                                f"{entry_label}.{key} is not read (known: type, damage, tick_interval, weather_multipliers)",
                            ))
                # Room-side numbers are *overrides* of the declared record, so they are
                # optional and only checked for being usable when present.
                for field, flat_name in (("damage", "hazard_damage"), ("tick_interval", "hazard_tick_interval")):
                    value = entry.get(field)
                    if value is None:
                        continue
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{entry_label} {flat_name if flat else field} must be a positive number",
                        ))
                weather_multipliers = entry.get("weather_multipliers")
                weather_key = "weather_hazard_multipliers" if flat else "weather_multipliers"
                if weather_multipliers is not None:
                    if not isinstance(weather_multipliers, dict):
                        issues.append(ContentSetIssue("error", str(path), f"{entry_label} {weather_key} must be an object"))
                    elif any(
                        not isinstance(weather, str) or not weather.strip()
                        or isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0
                        for weather, multiplier in weather_multipliers.items()
                    ):
                        issues.append(ContentSetIssue("error", str(path), f"{entry_label} {weather_key} requires non-empty weather names and positive numeric multipliers"))

                bite = _hazard_bite_problem(entry, declared_hazards.get(hazard_type), weather_multipliers)
                if bite:
                    issues.append(ContentSetIssue("warning", str(path), f"{entry_label} {bite}"))

    if required:
        for hazard_type in sorted(valid_hazards):
            if hazard_type not in authored_locations:
                issues.append(ContentSetIssue(
                    "error", str(elements_path),
                    f"hazard '{hazard_type}' is declared but is not used by any room",
                ))


def _hazard_bite_problem(entry: dict, record: Any, weather_multipliers: Any) -> str:
    """A sentence when a hazard would do nothing to a fresh hero, else "".

    Damage goes through the target's flat reduction first (`GameObject.take_damage`): the
    defence stat for a physical channel, the contract's resistance stat for any other. A hero
    starts with `PLAYER_BASE_DEFENSE` and `magic_resist` 2, so a hazard whose per-tick damage
    (the room's own number, else the declared one, at the weather's weakest) is not above
    that hurts nobody, and nothing tells the author. A background or gear can raise the
    floor, so this is a warning, and a set that means it can ignore it.
    """
    from engine.config.config_combat import HAZARD_DEFAULT_DAMAGE
    from engine.config.config_player import PLAYER_BASE_DEFENSE, PLAYER_DEFAULT_STATS

    def number(value: Any) -> Any:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None

    damage = number(entry.get("damage"))
    if damage is None and isinstance(record, dict):
        damage = number(record.get("damage"))
    if damage is None:
        damage = HAZARD_DEFAULT_DAMAGE
    factor = 1.0
    if isinstance(weather_multipliers, dict):
        weakest = [number(v) for v in weather_multipliers.values() if number(v) is not None]
        if weakest:
            factor = min(1.0, min(weakest))
    per_tick = max(1, int(round(float(damage) * factor)))
    channel = str(record.get("channel", "")).strip() if isinstance(record, dict) else ""
    physical = channel == "physical"
    floor = PLAYER_BASE_DEFENSE if physical else PLAYER_DEFAULT_STATS["magic_resist"]
    if per_tick > floor:
        return ""
    kind = "defence" if physical else "resistance"
    return (f"deals {per_tick} a tick at its weakest, which a fresh hero's flat {kind} of {floor} absorbs entirely: "
            f"it never hurts anyone (raise its damage above {floor})")


def _validate_district_contiguity(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A district's own rooms must be reachable from each other without ever
    leaving the district.

    `world.get_district` (engine/world/world.py) reads `properties.districts`
    purely as a named bag of member room ids -- nothing checks that those
    rooms actually form one connected area. A district that a player has to
    exit and re-enter through a different part of the map to fully see is a
    district in name only: shared district properties (ambient tone, a
    territory's atmosphere) apply to a room that geographically belongs to
    someone else's neighbourhood, and the "district" label stops meaning
    anything a player could point at. This is a structural defect, not a
    ruleset policy an author opts into, so it is checked unconditionally.
    """
    regions_dir = content_root / "regions"
    if not regions_dir.is_dir():
        return
    for path in sorted(regions_dir.glob("*.json")):
        payload = _load_json(path, issues, "region")
        if not isinstance(payload, dict) or isinstance(payload.get("themes"), dict):
            continue
        region_id = str(payload.get("region_id", "")).strip() or path.stem
        rooms = payload.get("rooms")
        if not isinstance(rooms, dict):
            continue
        properties = payload.get("properties")
        districts = properties.get("districts") if isinstance(properties, dict) else None
        if not isinstance(districts, dict):
            continue

        for district_id, district in districts.items():
            if not isinstance(district, dict):
                continue
            member_ids = district.get("members", district.get("rooms", []))
            if not isinstance(member_ids, list):
                continue
            members = {str(member_id) for member_id in member_ids}
            existing_members = {member_id for member_id in members if member_id in rooms}
            missing_members = members - existing_members
            for missing in sorted(missing_members):
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"region '{region_id}' district '{district_id}' names missing room '{missing}'",
                ))
            if len(existing_members) <= 1:
                continue

            # Edges within the district only: an exit or hidden exit whose
            # target is also a district member. Treated as undirected --
            # contiguity is about whether the area is one connected patch of
            # ground, not about one-way traversal within it.
            adjacency: dict[str, set[str]] = {member_id: set() for member_id in existing_members}
            for member_id in existing_members:
                room = rooms.get(member_id)
                if not isinstance(room, dict):
                    continue
                destinations: list[Any] = []
                exits = room.get("exits", {})
                if isinstance(exits, dict):
                    destinations.extend(exits.values())
                hidden_exits = (room.get("properties") or {}).get("hidden_exits", {})
                if isinstance(hidden_exits, dict):
                    destinations.extend(hidden_exits.values())
                for destination in destinations:
                    target = str(destination)
                    if ":" in target or target not in existing_members:
                        continue
                    adjacency[member_id].add(target)
                    adjacency[target].add(member_id)

            start = next(iter(existing_members))
            reached = {start}
            frontier = [start]
            while frontier:
                current = frontier.pop()
                for neighbour in adjacency.get(current, ()):
                    if neighbour not in reached:
                        reached.add(neighbour)
                        frontier.append(neighbour)

            unreached = existing_members - reached
            if unreached:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    "region '%s' district '%s' is not contiguous: %s cannot be reached from %s "
                    "without leaving the district"
                    % (region_id, district_id, ", ".join(sorted(unreached)), sorted(reached)[0]),
                ))


def validate_region_policy(content_root: Path | str, ruleset_path: Path | str) -> list[ContentSetIssue]:
    """Check every static region under ``content_root/regions`` against the
    region-authoring policy declared in ``ruleset_path`` (the same
    ``require_level_bands``/``require_classification``/
    ``require_hazard_coverage`` flags and biome/region_type vocabulary
    ``load_content_set`` reads), without requiring a full, loadable content
    set -- no manifest, no start room, no cross-file reference/reachability
    checks. Reuses the exact same per-region validators
    ``load_content_set`` calls internally; this only skips the checks that
    are inherently about the *whole* world (reachability from a start room,
    a hazard type defined but unused by any region anywhere) rather than
    about one region's own authored data.

    Meant for fast, standalone feedback while a region is still being
    authored or generated -- an editor's "validate before it's wired into
    the world" step. ``validate_content_set``/``load_content_set`` remain
    the complete, authoritative check once a full content set exists.
    """
    content_root = Path(content_root)
    ruleset_path = Path(ruleset_path)
    issues: list[ContentSetIssue] = []

    ruleset_payload = _load_json(ruleset_path, issues, "ruleset")
    if not isinstance(ruleset_payload, dict):
        return issues

    require_level_bands = _region_level_bands_required(ruleset_payload, issues, ruleset_path)
    require_hazard_coverage = _region_hazard_coverage_required(ruleset_payload, issues, ruleset_path)
    require_classification, biomes, region_types = _region_classification_policy(ruleset_payload, issues, ruleset_path)
    _validate_district_coverage_policy(ruleset_payload, issues, ruleset_path)

    _validate_region_level_bands(content_root, issues, required=require_level_bands)
    _validate_region_classification(content_root, issues, required=require_classification, biomes=biomes, region_types=region_types)
    _validate_region_hazard_coverage(content_root, issues, required=require_hazard_coverage)
    _validate_district_contiguity(content_root, issues)

    return issues
