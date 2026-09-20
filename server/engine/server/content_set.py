"""Runtime loading for versioned content-set packages.

The first contract supports a data root outside the package so that existing
world data can be wrapped and validated before it is migrated into a package.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTENT_SET_MANIFEST_NAME = "content_set.manifest.json"
CONTENT_SET_SCHEMA_VERSION = "1"
RUNTIME_API_VERSION = "1.0"
_CONTENT_SET_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_REQUIRED_DATA_DIRECTORIES = ("regions", "items", "npcs")
_CAPABILITY_SYSTEMS = ("inventory", "dialogue", "combat", "abilities", "magic", "crafting", "gathering", "quests", "collections", "discoveries", "social")
_RULESET_SYSTEMS = ("progression", "economy")
_DISABLED_PROGRESSION_MODELS = {"", "none", "off", "disabled"}


@dataclass(frozen=True)
class ContentSetIssue:
    severity: str
    path: str
    message: str


@dataclass(frozen=True)
class GameContract:
    """Normalized, client-safe description of a content set's game shape.

    Manifests describe what a package opts into while rulesets describe its
    rules.  Runtime code should consume this resolved contract instead of
    independently interpreting either source.
    """

    progression_model: str
    systems: tuple[tuple[str, bool], ...]
    status_fields: tuple[str, ...]
    ui_sections: tuple[str, ...]

    def system_enabled(self, system: str, default: bool = False) -> bool:
        return dict(self.systems).get(str(system).strip(), default)

    def to_payload(self) -> dict[str, Any]:
        return {
            "progression_model": self.progression_model,
            "systems": dict(self.systems),
            "status_fields": list(self.status_fields),
            "ui_sections": list(self.ui_sections),
        }


def _build_game_contract(
    capabilities: tuple[str, ...],
    ruleset: dict[str, Any],
    issues: list[ContentSetIssue],
    ruleset_path: Path,
) -> GameContract:
    """Resolve package declarations and report contradictory authored rules."""

    configured_systems = ruleset.get("systems", {}) if isinstance(ruleset, dict) else {}
    if not isinstance(configured_systems, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "ruleset.systems must be an object"))
        configured_systems = {}

    explicit: dict[str, bool] = {}
    for system, config in configured_systems.items():
        if not isinstance(config, dict) or "enabled" not in config:
            continue
        if not isinstance(config["enabled"], bool):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"ruleset.systems.{system}.enabled must be a boolean"))
            continue
        explicit[str(system).strip()] = config["enabled"]

    enabled_capabilities = set(capabilities)
    resolved: dict[str, bool] = {}
    for system in _CAPABILITY_SYSTEMS:
        declared = system in enabled_capabilities
        if system in explicit and explicit[system] != declared:
            issues.append(
                ContentSetIssue(
                    "error",
                    str(ruleset_path),
                    f"ruleset.systems.{system}.enabled conflicts with manifest capability '{system}'",
                )
            )
        resolved[system] = declared

    raw_model = ruleset.get("progression_model", "level_based") if isinstance(ruleset, dict) else "level_based"
    progression_model = str(raw_model).strip().lower()
    resolved["progression"] = progression_model not in _DISABLED_PROGRESSION_MODELS
    if "progression" in explicit and explicit["progression"] != resolved["progression"]:
        issues.append(
            ContentSetIssue(
                "error",
                str(ruleset_path),
                "ruleset.systems.progression.enabled conflicts with progression_model",
            )
        )
    # Economy is not a manifest capability because it has no loadable manager,
    # but is still a first-class game system in the canonical contract.
    resolved["economy"] = explicit.get("economy", True)
    for system, enabled in explicit.items():
        if system not in resolved:
            resolved[system] = enabled

    status_fields = ["name", "health"]
    if resolved["progression"]:
        status_fields.extend(("level", "experience"))
    if resolved.get("abilities") or resolved["magic"]:
        # One field for "this game shows the pool an ability spends". What the
        # pool *is* travels in the payload: a content set that declares charge
        # instead of mana must not be shown "mana" by a client that reads the
        # field list.
        status_fields.append("ability_resource")
    ui_sections = ["log", "nearby", "status"]
    if resolved["inventory"]:
        ui_sections.append("inventory")
    if resolved["quests"]:
        ui_sections.append("quests")
    if resolved["collections"]:
        ui_sections.append("collections")
    if resolved["discoveries"]:
        ui_sections.append("discoveries")
    if resolved["social"]:
        ui_sections.append("relationships")
    return GameContract(
        progression_model=progression_model or "none",
        systems=tuple(sorted(resolved.items())),
        status_fields=tuple(status_fields),
        ui_sections=tuple(ui_sections),
    )


@dataclass(frozen=True)
class ContentSetDefinition:
    manifest_path: Path
    package_root: Path
    content_set_id: str
    title: str
    version: str
    content_root: Path
    feature_profile_path: Path | None
    ruleset_path: Path
    ruleset: dict[str, Any]
    presentation_path: Path
    opening_path: Path | None
    opening: dict[str, Any]
    start_region_id: str
    start_room_id: str
    capabilities: tuple[str, ...]
    game_contract: GameContract


def _parse_version(value: Any) -> tuple[int, ...] | None:
    text = str(value).strip()
    if text == "":
        return None
    parts = text.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _runtime_in_range(runtime_api: str, minimum: str, maximum: str) -> bool:
    runtime = _parse_version(runtime_api)
    lower = _parse_version(minimum)
    upper = _parse_version(maximum)
    return runtime is not None and lower is not None and upper is not None and lower <= runtime <= upper


def _load_json(path: Path, issues: list[ContentSetIssue], label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        issues.append(ContentSetIssue("error", str(path), f"unable to read {label}: {exc}"))
    except json.JSONDecodeError as exc:
        issues.append(ContentSetIssue("error", str(path), f"invalid {label} JSON: {exc}"))
    return None


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
    """Validate room hazards against content-defined mappings and coverage.

    Only a ruleset that opts in has to place every mapped hazard. Whenever an
    elements file exists, individual room hazards are still checked for valid
    names and safe numeric timing/damage values.
    """
    elements_path = content_root / "combat" / "elements.json"
    if not elements_path.is_file():
        if required:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                "hazard coverage requires data/combat/elements.json with hazards.mapping",
            ))
        return

    elements_payload = _load_json(elements_path, issues, "combat elements")
    if not isinstance(elements_payload, dict):
        return
    hazards = elements_payload.get("hazards")
    mapping = hazards.get("mapping") if isinstance(hazards, dict) else None
    if not isinstance(mapping, dict):
        if required:
            issues.append(ContentSetIssue(
                "error", str(elements_path),
                "hazard coverage requires hazards.mapping to be an object",
            ))
        return

    valid_hazards: set[str] = set()
    for hazard_type in mapping:
        if isinstance(hazard_type, str) and hazard_type.strip():
            valid_hazards.add(hazard_type.strip())
        else:
            issues.append(ContentSetIssue(
                "error", str(elements_path), "hazards.mapping keys must be non-empty strings",
            ))
    if required and not valid_hazards:
        issues.append(ContentSetIssue(
            "error", str(elements_path), "hazard coverage requires at least one hazards.mapping entry",
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
            if not isinstance(properties, dict) or "hazard_type" not in properties:
                continue
            room_label = f"room '{region_id}:{room_id}'"
            hazard_type = properties.get("hazard_type")
            if not isinstance(hazard_type, str) or not hazard_type.strip():
                issues.append(ContentSetIssue(
                    "error", str(path), f"{room_label} hazard_type must be a non-empty string",
                ))
                continue
            hazard_type = hazard_type.strip()
            if hazard_type not in valid_hazards:
                issues.append(ContentSetIssue(
                    "error", str(path), f"{room_label} uses unknown hazard_type '{hazard_type}'",
                ))
                continue
            authored_locations.setdefault(hazard_type, []).append(f"{region_id}:{room_id}")
            for property_name in ("hazard_damage", "hazard_tick_interval"):
                value = properties.get(property_name)
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{room_label} {property_name} must be a positive number",
                    ))
            weather_multipliers = properties.get("weather_hazard_multipliers")
            if weather_multipliers is not None:
                if not isinstance(weather_multipliers, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{room_label} weather_hazard_multipliers must be an object"))
                elif any(
                    not isinstance(weather, str) or not weather.strip()
                    or isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0
                    for weather, multiplier in weather_multipliers.items()
                ):
                    issues.append(ContentSetIssue("error", str(path), f"{room_label} weather_hazard_multipliers requires non-empty weather names and positive numeric multipliers"))

    if required:
        for hazard_type in sorted(valid_hazards):
            if hazard_type not in authored_locations:
                issues.append(ContentSetIssue(
                    "error", str(elements_path),
                    f"hazard '{hazard_type}' is defined in hazards.mapping but is not used by any room",
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

    _validate_region_level_bands(content_root, issues, required=require_level_bands)
    _validate_region_classification(content_root, issues, required=require_classification, biomes=biomes, region_types=region_types)
    _validate_region_hazard_coverage(content_root, issues, required=require_hazard_coverage)

    return issues


def _validate_authored_world(
    content_root: Path,
    start_region_id: str,
    start_room_id: str,
    issues: list[ContentSetIssue],
) -> None:
    """Validate cross-file references that are only meaningful as a complete game."""
    regions: dict[str, dict[str, Any]] = {}
    region_paths: dict[str, Path] = {}
    for path in sorted((content_root / "regions").glob("*.json")):
        payload = _load_json(path, issues, "region")
        if not isinstance(payload, dict):
            continue
        # Region-generation themes share the directory but are not static regions.
        if isinstance(payload.get("themes"), dict):
            continue
        region_id = str(payload.get("region_id", "")).strip()
        rooms = payload.get("rooms")
        if not region_id:
            issues.append(ContentSetIssue("error", str(path), "region requires a non-empty region_id"))
            continue
        if not isinstance(rooms, dict):
            issues.append(ContentSetIssue("error", str(path), f"region '{region_id}' requires a rooms object"))
            continue
        if region_id in regions:
            issues.append(ContentSetIssue("error", str(path), f"duplicate region_id '{region_id}'"))
            continue
        regions[region_id] = rooms
        region_paths[region_id] = path

    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)

    # Build an adjacency map first, then traverse outwards from the start room.
    #
    # The previous version of this check appended every room's exit targets to
    # the traversal queue while it was still *validating* those rooms. Anything
    # named as an exit target was therefore treated as reachable even when the
    # room it led from was itself unreachable -- so the check could never detect
    # a closed-off zone. That is exactly how five Portbridge rooms (including
    # the only quest giver for an entire campaign) shipped with no way in while
    # this validator reported the content set clean.
    adjacency: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for region_id, rooms in regions.items():
        for room_id, room in rooms.items():
            if not isinstance(room, dict):
                issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' must be an object"))
                continue
            exits = room.get("exits", {})
            if not isinstance(exits, dict):
                issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' exits must be an object"))
                continue

            neighbours: list[tuple[str, str]] = []
            for direction, destination in exits.items():
                if not isinstance(destination, str) or not destination.strip():
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"exit '{region_id}:{room_id}:{direction}' must name a destination room"))
                    continue
                target_region, separator, target_room = destination.partition(":")
                if not separator:
                    target_region, target_room = region_id, target_region
                if target_region not in regions or target_room not in regions[target_region]:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"exit '{region_id}:{room_id}:{direction}' targets missing room '{destination}'"))
                else:
                    neighbours.append((target_region, target_room))

            # `properties.hidden_exits` are real traversable links (a lever
            # opens one, for example). Treating them as edges keeps a
            # mechanism-gated room from being reported as unreachable.
            hidden_exits = (room.get("properties") or {}).get("hidden_exits", {})
            if isinstance(hidden_exits, dict):
                for direction, destination in hidden_exits.items():
                    if not isinstance(destination, str) or not destination.strip():
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"hidden exit in '{region_id}:{room_id}' must name a destination room"))
                        continue
                    target_region, separator, target_room = destination.partition(":")
                    if not separator:
                        target_region, target_room = region_id, target_region
                    if target_region not in regions or target_room not in regions[target_region]:
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"hidden exit in '{region_id}:{room_id}' targets missing room '{destination}'"))
                    else:
                        neighbours.append((target_region, target_room))

            adjacency[(region_id, room_id)] = neighbours

            for npc in room.get("initial_npcs", []):
                if not isinstance(npc, dict) or not isinstance(npc.get("template_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid initial_npcs entry"))
                elif npc["template_id"] not in npc_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing NPC template '{npc['template_id']}'"))
                elif "overrides" in npc and not isinstance(npc["overrides"], dict):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' initial NPC overrides must be an object"))
            for item in room.get("items", []):
                if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid items entry"))
                elif item["item_id"] not in item_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing item '{item['item_id']}'"))

    reachable: set[tuple[str, str]] = set()
    pending = [(start_region_id, start_room_id)]
    while pending:
        location = pending.pop()
        if location in reachable:
            continue
        reachable.add(location)
        pending.extend(adjacency.get(location, ()))

    for region_id, rooms in regions.items():
        for room_id, room in rooms.items():
            if (region_id, room_id) in reachable:
                continue
            # A room may legitimately be entered by a system rather than by
            # walking: a jail cell is reached through the custody flow, with no
            # public exit leading in. Such a room must say so explicitly, so an
            # accidental omission (a zone with no door, which once orphaned five
            # Portbridge rooms and an entire campaign) is an error rather than
            # something that quietly ships.
            entered_by_system = None
            if isinstance(room, dict):
                entered_by_system = (room.get("properties") or {}).get("entered_by_system")
            if isinstance(entered_by_system, str) and entered_by_system.strip():
                continue
            issues.append(ContentSetIssue(
                "error",
                str(region_paths[region_id]),
                (
                    f"room '{region_id}:{room_id}' is not reachable from the declared start "
                    f"'{start_region_id}:{start_room_id}'. Add an exit leading to it, or declare "
                    f'properties.entered_by_system (e.g. "custody") if another system places the '
                    f"player there."
                ),
            ))


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


def _validate_weather_profiles(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """A `weather_profile` a region selects must be one the ruleset declares.

    `WeatherManager` looks the id up and falls back to the unmapped global
    weather, which is a reasonable default and also completely invisible: a
    region authored to have alpine weather just reports rain.
    """
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


def _validate_ruleset_references(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate optional cross-file references made by generic ruleset systems."""
    quest_generation = ruleset.get("quest_generation", {})
    if not isinstance(quest_generation, dict):
        return
    configured = quest_generation.get("authored_board_templates", [])
    if configured is None:
        return
    if not isinstance(configured, list):
        issues.append(ContentSetIssue("error", str(ruleset_path), "quest_generation.authored_board_templates must be an array"))
        return
    quest_ids = _load_definition_ids(content_root / "quests", "quest definitions", issues)
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    for index, entry in enumerate(configured):
        label = f"quest_generation.authored_board_templates[{index}]"
        if not isinstance(entry, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            continue
        template_id = entry.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.template_id must be a non-empty string"))
        elif template_id not in quest_ids:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} references missing quest template '{template_id}'"))
        giver_template_id = entry.get("giver_template_id")
        if giver_template_id is not None and (not isinstance(giver_template_id, str) or not giver_template_id.strip()):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.giver_template_id must be a non-empty string when provided"))
        elif isinstance(giver_template_id, str) and giver_template_id not in npc_ids:
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} references missing NPC template '{giver_template_id}'"))
        if "relationship_min" in entry:
            relationship_min = entry["relationship_min"]
            if isinstance(relationship_min, bool) or not isinstance(relationship_min, int) or relationship_min < 0 or relationship_min > 100:
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.relationship_min must be an integer from 0 to 100"))
        if "repeatable" in entry:
            repeatable = entry["repeatable"]
            if not isinstance(repeatable, dict):
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.repeatable must be an object"))
                continue
            delay_seconds = repeatable.get("delay_seconds")
            if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or delay_seconds <= 0:
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.repeatable.delay_seconds must be a positive number"))
            unavailable_text = repeatable.get("unavailable_text")
            if not isinstance(unavailable_text, str) or not unavailable_text.strip():
                issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.repeatable.unavailable_text must be a non-empty string"))


def _validate_ambient_loot_references(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate generic, content-authored ambient loot pools."""
    loot = ruleset.get("loot", {})
    if loot is None:
        return
    if not isinstance(loot, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "loot must be an object"))
        return
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


def _condition_issues(node: Any, where: str, path: Path) -> list[ContentSetIssue]:
    """Walk a condition tree and report every malformed or unknown node.

    Shared by titles (P4) and dialogue (P5): both gate content on the same
    predicate language, and a typo in either must fail validation rather than
    silently leave a gate shut (or, worse, open).
    """
    from engine.conditions import KNOWN_KINDS

    found: list[ContentSetIssue] = []

    def walk(current: Any, label: str) -> None:
        if current is None or isinstance(current, (str, int, float, bool)):
            return
        if isinstance(current, list):
            for index, child in enumerate(current):
                walk(child, "%s[%d]" % (label, index))
            return
        if not isinstance(current, dict):
            found.append(ContentSetIssue("error", str(path), f"{label} must be a condition object"))
            return
        for composite in ("all", "any"):
            if composite in current:
                walk(current[composite], "%s.%s" % (label, composite))
                return
        if "not" in current:
            walk(current["not"], "%s.not" % label)
            return
        kind = str(current.get("kind", "")).strip()
        if not kind:
            found.append(ContentSetIssue("error", str(path), f"{label} has no 'kind'"))
        elif kind not in KNOWN_KINDS:
            found.append(ContentSetIssue(
                "error", str(path),
                f"{label} uses unknown condition kind '{kind}' "
                f"(known: {', '.join(sorted(KNOWN_KINDS))})",
            ))

    walk(node, where)
    return found


def _ability_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    """Every ability id this set defines, read from the files the engine reads.

    Not from `SPELL_REGISTRY`: that registry is populated when a `World` boots,
    and validation runs *before* one exists (`game_manager.py` loads the content
    set, then constructs the world). Reading it here returned an empty set, and
    an empty id set means "skip this check" -- so every `spell_known`,
    `teach_spell` and `known_spells` reference in the game was unchecked while
    the validator reported success.

    The directory choice mirrors `load_spells_from_json`: `abilities/` is what a
    set that does not call them spells uses, `magic/` is the older name, and the
    first one that exists wins.
    """
    for candidate in ("abilities", "magic"):
        directory = content_root / candidate
        if not directory.is_dir():
            continue
        ability_ids: set[str] = set()
        for path in sorted(directory.glob("*.json")):
            payload = _load_json(path, issues, "ability definitions")
            if isinstance(payload, dict):
                ability_ids |= {str(k) for k in payload if not str(k).startswith("_")}
        return ability_ids
    return set()


def _content_identifier_sets(content_root: Path, issues: list[ContentSetIssue]) -> dict[str, set[str]]:
    """Every id a dialogue line might name, gathered once."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    recipe_ids: set[str] = set()
    crafting_dir = content_root / "crafting"
    if crafting_dir.is_dir():
        for path in sorted(crafting_dir.glob("*.json")):
            payload = _load_json(path, issues, "crafting recipes")
            if isinstance(payload, dict):
                recipe_ids |= {str(k) for k in payload if not str(k).startswith("_")}

    quest_ids: set[str] = set()
    quest_path = content_root / "quests" / "quests.json"
    if quest_path.is_file():
        payload = _load_json(quest_path, issues, "quest definitions")
        if isinstance(payload, dict):
            quest_ids |= {str(k) for k in payload if not str(k).startswith("_")}

    # Campaign ids come from the files the *engine* reads: `campaigns/*.json`,
    # keyed by each file's `campaign_id` (`campaign_manager.py`). This used to
    # look in `quests/campaigns/` and `quests/campaigns.json`, neither of which
    # exists in any shipped set -- so the bucket was always empty, and the reader
    # that guards on a non-empty bucket (`_stage_objectives` and friends) turned
    # every `start_campaign` reference into a no-op. An empty id set that means
    # "skip the check" is the worst possible failure: the check reports success.
    campaign_ids: set[str] = set()
    campaigns_dir = content_root / "campaigns"
    if campaigns_dir.is_dir():
        for path in sorted(campaigns_dir.glob("*.json")):
            payload = _load_json(path, issues, "campaign definitions")
            if not isinstance(payload, dict):
                continue
            # A campaign file may be one campaign or a library of them: the
            # engine keys a campaign by the file's own `campaign_id` when it has
            # one, and by the entry's key otherwise.
            authored = payload.get("campaign_id")
            if isinstance(authored, str) and authored.strip():
                campaign_ids.add(authored.strip())
                continue
            for key, definition in payload.items():
                if str(key).startswith("_"):
                    continue
                nested = definition.get("campaign_id") if isinstance(definition, dict) else None
                campaign_ids.add(str(nested) if isinstance(nested, str) and nested.strip() else str(key))

    discovery_ids: set[str] = set()
    discoveries_path = content_root / "discoveries.json"
    if discoveries_path.is_file():
        payload = _load_json(discoveries_path, issues, "discoveries")
        if isinstance(payload, dict):
            discovery_ids |= {str(k) for k in payload if not str(k).startswith("_")}

    region_ids: set[str] = set()
    regions_dir = content_root / "regions"
    if regions_dir.is_dir():
        for path in sorted(regions_dir.glob("*.json")):
            payload = _load_json(path, issues, "region definitions")
            if isinstance(payload, dict):
                region_id = payload.get("region_id")
                if isinstance(region_id, str) and region_id.strip():
                    region_ids.add(region_id)
                else:
                    region_ids.add(path.stem)

    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    return {
        "items": item_ids,
        "recipes": recipe_ids,
        "quests": quest_ids,
        "campaigns": campaign_ids,
        "discoveries": discovery_ids,
        "regions": region_ids,
        "npcs": npc_ids,
        "spells": _ability_ids(content_root, issues),
    }


def _validate_dialogue_content(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate authored conversations, their references, and their wiring.

    The point is the P5 definition of done: a missing graph, a `next_node` that
    does not exist, a condition kind the engine cannot evaluate, or an effect
    naming an item nobody authored must fail *validation*, never a conversation.
    A player should not be the one who discovers that a choice leads nowhere.
    """
    from engine.dialogue.effects import KNOWN_EFFECTS
    from engine.dialogue.manager import parse_graph

    dialogue_dir = content_root / "dialogue"
    graphs: dict[str, Any] = {}
    graph_paths: dict[str, Path] = {}

    if dialogue_dir.is_dir():
        for path in sorted(dialogue_dir.glob("*.json")):
            payload = _load_json(path, issues, "dialogue graphs")
            if payload is None:
                continue
            graph_id = str(payload.get("id") or path.stem) if isinstance(payload, dict) else path.stem
            graph, graph_issues = parse_graph(payload, graph_id, path.name)
            for issue in graph_issues:
                issues.append(ContentSetIssue("error", str(path), issue))
            if graph is None:
                continue
            if graph_id in graphs:
                issues.append(ContentSetIssue(
                    "error", str(path), f"duplicate dialogue graph id '{graph_id}'"
                ))
                continue
            graphs[graph_id] = graph
            graph_paths[graph_id] = path

    ids = _content_identifier_sets(content_root, issues)

    # A graph nobody points at is dead content; a pointer to no graph is a
    # broken conversation. The second is an error, the first a warning.
    referenced: set[str] = set()
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue
            properties = template.get("properties")
            if not isinstance(properties, dict):
                continue
            graph_id = str(properties.get("dialogue", "") or "").strip()
            if not graph_id:
                continue
            referenced.add(graph_id)
            if graph_id not in graphs:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"NPC '{template_id}' references missing dialogue graph '{graph_id}'",
                ))

    for graph_id, graph in graphs.items():
        path = graph_paths[graph_id]
        label = f"dialogue graph '{graph_id}'"
        if graph_id not in referenced:
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{label} is not referenced by any NPC template",
            ))
        for node in graph.nodes.values():
            where = f"{label} node '{node.node_id}'"

            def check_condition(node_or_block, where_label):
                for issue in _condition_issues(node_or_block, where_label, path):
                    issues.append(issue)
                for kind, key, bucket in (
                    ("has_item", "item_id", "items"),
                    ("knows_recipe", "recipe_id", "recipes"),
                    ("spell_known", "spell_id", "spells"),
                    ("quest_completed", "quest_id", "quests"),
                    ("quest_active", "quest_id", "quests"),
                    ("discovery", "discovery_id", "discoveries"),
                    ("visited_region", "region_id", "regions"),
                    ("in_region", "region_id", "regions"),
                    ("relationship_at_least", "npc_id", "npcs"),
                ):
                    current = node_or_block
                    if not isinstance(current, dict) or str(current.get("kind", "")) != kind:
                        continue
                    identifier = str(current.get(key, "") or "").strip()
                    if identifier and ids[bucket] and identifier not in ids[bucket]:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{where_label} names {key} '{identifier}', which is not defined in this content set",
                        ))

            def check_effects(block, where_label):
                if not isinstance(block, dict):
                    return
                for key in sorted(block):
                    if key not in KNOWN_EFFECTS:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{where_label} has unknown effect '{key}' "
                            f"(known: {', '.join(sorted(KNOWN_EFFECTS))})",
                        ))
                for key, bucket in (
                    ("grant_recipe", "recipes"),
                    ("teach_spell", "spells"),
                    ("grant_discovery", "discoveries"),
                    ("start_quest", "quests"),
                    ("advance_quest", "quests"),
                    ("complete_quest", "quests"),
                    ("start_campaign", "campaigns"),
                    ("give_item", "items"),
                    ("take_item", "items"),
                ):
                    if key not in block:
                        continue
                    for identifier in _effect_identifiers(block[key]):
                        if ids[bucket] and identifier not in ids[bucket]:
                            issues.append(ContentSetIssue(
                                "error", str(path),
                                f"{where_label} effect {key} names '{identifier}', "
                                f"which is not defined in this content set",
                            ))
                rewards = block.get("give_rewards")
                if isinstance(rewards, dict):
                    for entry in rewards.get("items", []) or []:
                        identifier = entry.get("item_id") if isinstance(entry, dict) else entry
                        if isinstance(identifier, str) and ids["items"] and identifier not in ids["items"]:
                            issues.append(ContentSetIssue(
                                "error", str(path),
                                f"{where_label} effect give_rewards names item '{identifier}', "
                                f"which is not defined in this content set",
                            ))
                relationship = block.get("adjust_relationship")
                if isinstance(relationship, dict):
                    npc_id = str(relationship.get("npc", "") or "").strip()
                    if npc_id and ids["npcs"] and npc_id not in ids["npcs"]:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{where_label} effect adjust_relationship names NPC '{npc_id}', "
                            f"which is not defined in this content set",
                        ))
                move = block.get("move_npc")
                if isinstance(move, dict):
                    npc_id = str(move.get("npc", "") or "").strip()
                    region_id = str(move.get("region", "") or "").strip()
                    if npc_id and ids["npcs"] and npc_id not in ids["npcs"]:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{where_label} effect move_npc names NPC '{npc_id}', "
                            f"which is not defined in this content set",
                        ))
                    if region_id and ids["regions"] and region_id not in ids["regions"]:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{where_label} effect move_npc names region '{region_id}', "
                            f"which is not defined in this content set",
                        ))
                reveal = block.get("reveal_exit")
                if isinstance(reveal, dict):
                    _check_reveal_exit(reveal, where_label, content_root, path, issues)

            check_effects(node.effects, f"{where}.effects")
            for choice in node.choices:
                choice_where = f"{where}.choices[{choice.index}]"
                check_condition(choice.condition, f"{choice_where}.condition")
                check_effects(choice.effects, f"{choice_where}.effects")
                if choice.check:
                    check_effects(choice.check.get("success_effects"), f"{choice_where}.check.success_effects")
                    check_effects(choice.check.get("fail_effects"), f"{choice_where}.check.fail_effects")


def _effect_identifiers(value: Any) -> list[str]:
    """Ids named by one effect value, in any of its accepted shapes."""
    found: list[str] = []
    entries = value if isinstance(value, (list, tuple)) else [value]
    for entry in entries:
        if isinstance(entry, str):
            if entry.strip():
                found.append(entry.strip())
            continue
        if isinstance(entry, dict):
            identifier = str(
                entry.get("item_id") or entry.get("id") or entry.get("recipe_id")
                or entry.get("spell_id") or entry.get("discovery_id") or entry.get("quest_id") or ""
            ).strip()
            if identifier:
                found.append(identifier)
    return found


def _check_reveal_exit(
    reveal: dict[str, Any], where: str, content_root: Path, path: Path, issues: list[ContentSetIssue]
) -> None:
    """A `reveal_exit` must name a room that really has that hidden exit."""
    room_ref = str(reveal.get("room", "") or "").strip()
    direction = str(reveal.get("direction", "") or "").strip().lower()
    if not room_ref or not direction:
        issues.append(ContentSetIssue("error", str(path), f"{where} effect reveal_exit needs room and direction"))
        return
    region_id, _, room_id = room_ref.partition(":")
    if not room_id:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{where} effect reveal_exit.room must be 'region:room', got '{room_ref}'",
        ))
        return
    region_path = content_root / "regions" / f"{region_id}.json"
    if not region_path.is_file():
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} effect reveal_exit names missing region '{region_id}'"
        ))
        return
    payload = _load_json(region_path, issues, "region definitions")
    rooms = payload.get("rooms", {}) if isinstance(payload, dict) else {}
    room = rooms.get(room_id) if isinstance(rooms, dict) else None
    if not isinstance(room, dict):
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} effect reveal_exit names missing room '{room_ref}'"
        ))
        return
    hidden = (room.get("properties") or {}).get("hidden_exits", {})
    if not isinstance(hidden, dict) or direction not in hidden:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{where} effect reveal_exit opens '{direction}' in '{room_ref}', "
            f"but that room declares no hidden exit there",
        ))


def _validate_quest_stages(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Every stage must say what it is waiting for.

    A stage with neither `objective` nor `objectives_any` has no route to
    satisfaction, and `QuestManager.get_active_objectives` returns an empty list
    for it -- so the quest stops there forever. Nothing used to report it: the
    editor's quest inspector wrote exactly that shape (`type`, `target`, `count`,
    `next` at stage level) and content validation passed with zero errors, which
    made a broken quest look finished. The world editor was fixed to write
    `objective`; this is the engine refusing to accept a stage without one.
    """
    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                issues.append(ContentSetIssue(
                    "error", str(quests_path),
                    f"quest '{quest_id}' stage {index} must be an object",
                ))
                continue
            if _stage_objectives(stage):
                continue
            unknown = sorted(
                key for key in stage
                if key in ("type", "target", "count", "next", "id")
            )
            hint = (
                " It carries %s, which is not a stage field the engine reads."
                % ", ".join(unknown)
            ) if unknown else ""
            issues.append(ContentSetIssue(
                "error", str(quests_path),
                f"quest '{quest_id}' stage {index} declares neither 'objective' nor "
                f"'objectives_any', so nothing can satisfy it.{hint}",
            ))


def _validate_quest_choice_outcomes(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A branching objective must say where each of its outcomes leads.

    `negotiate` and `dialogue_choice` objectives resolve to one of several
    authored outcomes, and each outcome decides what happens next. Omitting
    `next_stage` used to fall back to "the stage after this one", which is a
    silent *lie* whenever the next stage is the violent option: a successful
    truce in `quest_bandit_lieutenant` advanced to "Kill the Lieutenant", and
    the campaign's PEACEFUL_SUCCESS transition on that node could never fire.

    So: every outcome must declare `next_stage` (move on), or `complete: true`
    (this ends the quest). Anything else is an authoring error rather than a
    default the author never chose.
    """
    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            for objective in _stage_objectives(stage):
                if str(objective.get("type", "")) not in ("negotiate", "dialogue_choice"):
                    continue
                choices = objective.get("choices")
                label = f"quest '{quest_id}' stage {index} ({objective.get('type')})"
                if not isinstance(choices, dict) or not choices:
                    issues.append(ContentSetIssue(
                        "error", str(quests_path),
                        f"{label} has no choices to resolve",
                    ))
                    continue
                for outcome, branch in choices.items():
                    where = f"{label} outcome '{outcome}'"
                    if not isinstance(branch, dict):
                        issues.append(ContentSetIssue("error", str(quests_path), f"{where} must be an object"))
                        continue
                    next_stage = branch.get("next_stage")
                    completes = bool(branch.get("complete", False))
                    if next_stage is None and not completes:
                        issues.append(ContentSetIssue(
                            "error", str(quests_path),
                            f"{where} must declare next_stage or complete: true -- "
                            f"otherwise it silently advances to the next stage",
                        ))
                        continue
                    if next_stage is not None:
                        if isinstance(next_stage, bool) or not isinstance(next_stage, int):
                            issues.append(ContentSetIssue(
                                "error", str(quests_path), f"{where}.next_stage must be an integer",
                            ))
                        elif not (0 <= next_stage <= len(stages)):
                            issues.append(ContentSetIssue(
                                "error", str(quests_path),
                                f"{where}.next_stage {next_stage} is outside this quest's "
                                f"{len(stages)} stages",
                            ))


def _stage_objectives(stage: dict) -> list[dict]:
    """Every objective a stage routes through (compact `objective` or
    `objectives_any`)."""
    found: list[dict] = []
    objective = stage.get("objective")
    if isinstance(objective, dict):
        found.append(objective)
    alternatives = stage.get("objectives_any")
    if isinstance(alternatives, list):
        found.extend(entry for entry in alternatives if isinstance(entry, dict))
    return found


def _load_recipes(content_root: Path, issues: list[ContentSetIssue]) -> dict[str, dict]:
    recipes: dict[str, dict] = {}
    crafting_dir = content_root / "crafting"
    if not crafting_dir.is_dir():
        return recipes
    for path in sorted(crafting_dir.glob("*.json")):
        payload = _load_json(path, issues, "crafting recipes")
        if not isinstance(payload, dict):
            continue
        for recipe_id, recipe in payload.items():
            if isinstance(recipe, dict) and not str(recipe_id).startswith("_"):
                recipes[str(recipe_id)] = recipe
    return recipes


def _validate_new_quest_objective_types(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate the five reused-infrastructure objective types added in P6:
    relationship, discover_n, craft_quality, gather_types, deliver_multi.

    Each reuses an existing tracked value (relationship score, advancement
    ledger, recipe quality tiers, resource item ids, NPC templates) rather
    than inventing new player state, so validation is mostly "does this
    reference something real."
    """
    from engine.core.advancement import KNOWN_ENTRY_KINDS

    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    recipes = _load_recipes(content_root, issues)

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            for objective in _stage_objectives(stage):
                obj_type = str(objective.get("type", ""))
                label = f"quest '{quest_id}' stage {index} ({obj_type})"

                if obj_type == "relationship":
                    target = objective.get("target_npc_template_id")
                    if not isinstance(target, str) or target not in npc_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.target_npc_template_id references a missing NPC template"))
                    score = objective.get("required_score")
                    if isinstance(score, bool) or not isinstance(score, int):
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_score must be an integer"))

                elif obj_type == "discover_n":
                    kind = objective.get("kind")
                    if kind not in KNOWN_ENTRY_KINDS:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.kind must be one of {sorted(KNOWN_ENTRY_KINDS)}"))
                    count = objective.get("required_count")
                    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_count must be a positive integer"))

                elif obj_type == "craft_quality":
                    recipe_id = objective.get("recipe_id")
                    recipe = recipes.get(recipe_id) if isinstance(recipe_id, str) else None
                    if recipe is None:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipe_id references a missing recipe"))
                        continue
                    required_quality_id = objective.get("required_quality_id")
                    tiers = recipe.get("quality_tiers", [])
                    tier_ids = {tier.get("id") for tier in tiers if isinstance(tier, dict)}
                    if not isinstance(required_quality_id, str) or required_quality_id not in tier_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_quality_id must name one of {recipe_id}'s quality_tiers ids"))

                elif obj_type == "gather_types":
                    required_ids = objective.get("required_item_ids")
                    if not isinstance(required_ids, list) or not required_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_item_ids must be a non-empty array"))
                    else:
                        for item_id in required_ids:
                            if not isinstance(item_id, str) or item_id not in item_ids:
                                issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_item_ids references a missing item template: {item_id!r}"))

                elif obj_type == "deliver_multi":
                    item_template_id = objective.get("item_template_id")
                    if not isinstance(item_template_id, str) or item_template_id not in item_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.item_template_id references a missing item template"))
                    recipients = objective.get("recipients")
                    if not isinstance(recipients, list) or len(recipients) < 2:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipients must be an array of at least 2 entries"))
                    else:
                        for r_index, recipient in enumerate(recipients):
                            if not isinstance(recipient, dict) or recipient.get("template_id") not in npc_ids:
                                issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipients[{r_index}].template_id references a missing NPC template"))


def _validate_contract_content(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate declared contracts, and the templates that reference them.

    The registry refuses to guess (see `engine/contracts/registry.py`): a version
    it does not know, a field its schema does not define, a profile pointing at a
    family that does not exist. This turns those refusals into content errors,
    and adds the one check the registry cannot make about itself — that a family
    names an item class the engine actually has.

    A template's own `item_family` / `generation_profile` are checked here too,
    so a typo fails the build rather than resolving to nothing at runtime.
    """
    from engine.contracts import ContractRegistry

    contracts_path = content_root / "contracts" / "world_contracts.json"
    registry = ContractRegistry.load(str(content_root))
    for issue in registry.issues:
        issues.append(ContentSetIssue("error", str(contracts_path), issue))

    if registry.is_empty:
        return

    from engine.items.item_factory import ITEM_CLASS_MAP

    for family_id, family in registry.item_families.items():
        item_class = str(family.get("item_class", "") or "")
        if item_class and item_class not in ITEM_CLASS_MAP:
            issues.append(ContentSetIssue(
                "error", str(contracts_path),
                f"item_families.{family_id}.item_class '{item_class}' is not an item class "
                f"this engine has (known: {', '.join(sorted(ITEM_CLASS_MAP))})",
            ))

    items_dir = content_root / "items"
    if not items_dir.is_dir():
        return
    for path in sorted(items_dir.glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, template in payload.items():
            if str(item_id).startswith("_") or not isinstance(template, dict):
                continue
            family_id = str(template.get("item_family", "") or "")
            if family_id and family_id not in registry.item_families:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"item '{item_id}' declares item_family '{family_id}', which this "
                    f"content set does not define",
                ))
            profile_id = str(template.get("generation_profile", "") or "")
            if profile_id and profile_id not in registry.generation_profiles:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"item '{item_id}' declares generation_profile '{profile_id}', which "
                    f"this content set does not define",
                ))
            # A family that generates instances needs a profile to roll from, or
            # every instance of it comes out undifferentiated.
            if family_id and family_id in registry.item_families:
                family = registry.item_families[family_id]
                capabilities = family.get("capabilities") or []
                family_profile = str(family.get("generation_profile", "") or "")
                if "generated_instance" in capabilities and not (family_profile or profile_id):
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"item '{item_id}' is in family '{family_id}', which generates "
                        f"instances, but neither it nor the family declares a generation profile",
                    ))


def _validate_vendor_orders(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate optional, setting-agnostic vendor delivery orders."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for npc_id, definition in payload.items():
            if not isinstance(definition, dict):
                continue
            properties = definition.get("properties", {})
            orders = properties.get("buy_orders", []) if isinstance(properties, dict) else []
            if not orders:
                continue
            label = f"NPC '{npc_id}'.properties.buy_orders"
            if not isinstance(orders, list):
                issues.append(ContentSetIssue("error", str(path), f"{label} must be an array"))
                continue
            seen: set[str] = set()
            for index, order in enumerate(orders):
                entry = f"{label}[{index}]"
                if not isinstance(order, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry} must be an object"))
                    continue
                order_id = order.get("id")
                if not isinstance(order_id, str) or not order_id.strip():
                    issues.append(ContentSetIssue("error", str(path), f"{entry}.id must be a non-empty string"))
                elif order_id in seen:
                    issues.append(ContentSetIssue("error", str(path), f"{label} ids must be unique"))
                else:
                    seen.add(order_id)
                # An order asks for an item the same way a recipe ingredient
                # does: an exact template, a family, or a capability, with an
                # optional material-grade floor. `min_material_quality` and the
                # older `min_material_quality_score` are both read; the
                # reference helper checks whichever is present.
                issues.extend(_item_reference_issues(
                    order, entry, path, item_ids, _load_contract_registry(content_root),
                ))
                for field in ("quantity", "reward_gold"):
                    value = order.get(field)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (field == "quantity" and value < 1):
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.{field} must be a valid non-negative integer"))
                for field in ("repeatable", "crafted_only"):
                    if field in order and not isinstance(order[field], bool):
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.{field} must be a boolean"))
                # The quality floor is checked by `_item_reference_issues` above,
                # for both spellings. Checking it again here reported the same
                # bad value twice, which reads as two problems in the content.


def _validate_salvage_rules(
    content_root: Path,
    issues: list[ContentSetIssue],
    registry: Any = None,
    ruleset_path: Optional[Path] = None,
    ruleset_payload: Any = None,
) -> None:
    """Validate what an item breaks down into.

    Until now nothing checked any of this, so a typo'd key fell silently through
    to the set's scrap default and a rule naming a missing template failed only
    when a player tried it. Salvage output is an item reference -- the same shape
    a recipe ingredient uses -- and is checked the same way.
    """
    if ruleset_path is None:
        return
    ruleset_path = Path(ruleset_path)
    payload = ruleset_payload
    crafting = payload.get("crafting") if isinstance(payload, dict) else None
    rules = crafting.get("salvage_rules") if isinstance(crafting, dict) else None
    if rules is None:
        return
    if not isinstance(rules, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), "crafting.salvage_rules must be an object"))
        return

    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    label = "crafting.salvage_rules"

    default_id = rules.get("default_item_id")
    if default_id is not None:
        if not isinstance(default_id, str) or default_id not in item_ids:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.default_item_id references a missing item template",
            ))

    from engine.items.item_factory import ITEM_CLASS_MAP

    by_family = rules.get("by_family", {})
    if not isinstance(by_family, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), f"{label}.by_family must be an object"))
        by_family = {}
    for family_id, rule in by_family.items():
        if str(family_id).startswith("_"):
            continue
        entry = f"{label}.by_family.{family_id}"
        if registry is None or not registry.family(str(family_id)):
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{entry} is not an item family this content set declares",
            ))
        issues.extend(_salvage_rule_issues(rule, entry, ruleset_path, item_ids, registry))

    for key, rule in rules.items():
        if key in ("by_family", "default_item_id") or str(key).startswith("_"):
            continue
        entry = f"{label}.{key}"
        if key not in ITEM_CLASS_MAP:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{entry} is not an item class this engine has (known: {', '.join(sorted(ITEM_CLASS_MAP))}); "
                f"use by_family to key a rule on what a thing *is*",
            ))
        issues.extend(_salvage_rule_issues(rule, entry, ruleset_path, item_ids, registry))


def _salvage_rule_issues(
    rule: object,
    entry: str,
    path: Path,
    item_ids: set[str],
    registry: Any = None,
) -> list[ContentSetIssue]:
    """Validate one salvage rule: what it produces, and how much."""
    issues: list[ContentSetIssue] = []
    if not isinstance(rule, dict):
        issues.append(ContentSetIssue("error", str(path), f"{entry} must be an object"))
        return issues
    issues.extend(_item_reference_issues(rule, entry, path, item_ids, registry, quantity_field=None))
    if "quantity_per_weight" in rule:
        rate = rule["quantity_per_weight"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0:
            issues.append(ContentSetIssue(
                "error", str(path), f"{entry}.quantity_per_weight must be a non-negative number",
            ))
    return issues


def _validate_item_salvage_outputs(content_root: Path, issues: list[ContentSetIssue], registry: Any = None) -> None:
    """Validate an item template's own `salvage_output` property."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, definition in payload.items():
            if not isinstance(definition, dict) or str(item_id).startswith("_"):
                continue
            properties = definition.get("properties", {})
            if not isinstance(properties, dict) or "salvage_output" not in properties:
                continue
            entry = f"item '{item_id}'.properties.salvage_output"
            issues.extend(
                _salvage_rule_issues(properties["salvage_output"], entry, path, item_ids, registry)
            )


def _validate_resource_node_yields(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate portable resource-node yield and material-grade contracts."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)

    def validate_quality(value: Any, path: Path, label: str) -> None:
        if not isinstance(value, dict):
            issues.append(ContentSetIssue("error", str(path), f"{label}.material_quality must be an object"))
            return
        quality_id = value.get("id")
        quality_label = value.get("label")
        score = value.get("score")
        if not isinstance(quality_id, str) or not quality_id.strip():
            issues.append(ContentSetIssue("error", str(path), f"{label}.material_quality.id must be a non-empty string"))
        if not isinstance(quality_label, str) or not quality_label.strip():
            issues.append(ContentSetIssue("error", str(path), f"{label}.material_quality.label must be a non-empty string"))
        if isinstance(score, bool) or not isinstance(score, int) or score < 1:
            issues.append(ContentSetIssue("error", str(path), f"{label}.material_quality.score must be a positive integer"))

    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, definition in payload.items():
            if not isinstance(definition, dict) or definition.get("type") != "ResourceNode":
                continue
            properties = definition.get("properties", {})
            if not isinstance(properties, dict):
                continue
            label = f"resource node '{item_id}'"
            resource_item_id = properties.get("resource_item_id")
            if not isinstance(resource_item_id, str) or resource_item_id not in item_ids:
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties.resource_item_id references a missing item template"))
            if "substitute_resource_ids" in properties:
                substitute_ids = properties["substitute_resource_ids"]
                if not isinstance(substitute_ids, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.substitute_resource_ids must be an array"))
                else:
                    for substitute_id in substitute_ids:
                        if not isinstance(substitute_id, str) or substitute_id not in item_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{label}.properties.substitute_resource_ids references a missing item template: {substitute_id!r}"))
            if "material_quality" in properties:
                validate_quality(properties["material_quality"], path, label)
            yields = properties.get("yield_table", [])
            if not isinstance(yields, list):
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties.yield_table must be an array"))
                continue
            for index, candidate in enumerate(yields):
                entry = f"{label}.properties.yield_table[{index}]"
                if not isinstance(candidate, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry} must be an object"))
                    continue
                candidate_item_id = candidate.get("item_id")
                if not isinstance(candidate_item_id, str) or candidate_item_id not in item_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{entry}.item_id references a missing item template"))
                chance = candidate.get("chance")
                if isinstance(chance, bool) or not isinstance(chance, (int, float)) or not 0 <= chance <= 1:
                    issues.append(ContentSetIssue("error", str(path), f"{entry}.chance must be a number from 0 to 1"))
                if "material_quality" in candidate:
                    validate_quality(candidate["material_quality"], path, entry)


def _validate_advancement_content(content_root: Path, ruleset: dict[str, Any], issues: list[ContentSetIssue], ruleset_path: Path) -> None:
    """Validate the authored activity-XP table.

    Two mistakes are worth catching here rather than in play, because both fail
    *silently*: a rule whose kind no engine system records pays nothing forever,
    and a rule whose kind is unrecognised is rejected outright. Either way the
    activity looks supported in the ruleset and rewards nothing in the game.
    """
    from engine.core.advancement import KNOWN_ENTRY_KINDS

    section = ruleset.get("advancement", {})
    if section is None:
        return
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


def _load_contract_registry(content_root: Path) -> Any:
    """The content set's contract registry, or None when it cannot be read.

    `_validate_contract_content` loads contracts to check them; every later
    check that has to resolve a family or a capability against them comes
    through here, so the file is parsed once per validation run rather than once
    per caller. Cached on the file's mtime so a long-lived process -- the editor
    validating content it just saved -- cannot answer from a stale copy.
    """
    contracts_path = content_root / "contracts" / "world_contracts.json"
    try:
        stamp = contracts_path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(contracts_path), stamp)
    if key in _CONTRACT_REGISTRY_CACHE:
        return _CONTRACT_REGISTRY_CACHE[key]
    try:
        from engine.contracts import ContractRegistry

        registry = ContractRegistry.load(str(content_root))
    except Exception:
        return None
    _CONTRACT_REGISTRY_CACHE.clear()
    _CONTRACT_REGISTRY_CACHE[key] = registry
    return registry


def _item_reference_issues(
    reference: object,
    entry: str,
    path: Path,
    item_ids: set[str],
    registry: Any = None,
    *,
    quantity_field: Optional[str] = "quantity",
) -> list[ContentSetIssue]:
    """Validate one authored item reference -- what it asks for, and whether it lands.

    A reference names either an exact template, a family, or a capability. It is
    the same shape wherever content asks for an item: a recipe ingredient, a
    vendor's buy order, a salvage rule's output. `item_id` wins when present (so
    content written before families existed resolves exactly as it did), which is
    why naming two kinds at once is a warning rather than an error: the extra
    reference is dead weight the author probably did not intend, but nothing
    misbehaves at runtime.

    `quantity_field` is the key that says how many units are wanted, which is
    `quantity` almost everywhere and nothing at all for a salvage rule (which
    yields by weight instead). Pass None to skip that check.
    """
    from engine.items import references

    issues: list[ContentSetIssue] = []
    if not isinstance(reference, dict):
        issues.append(ContentSetIssue("error", str(path), f"{entry} must be an object"))
        return issues

    kind = references.reference_kind(reference)
    if not kind:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{entry} names nothing: give it an item_id, an item_family, or a capability",
        ))
        return issues

    given = [
        key for key in references.REFERENCE_KEYS
        if str(reference.get(key, "") or "").strip()
    ]
    if len(given) > 1:
        issues.append(ContentSetIssue(
            "warning", str(path),
            f"{entry} names {' and '.join(given)}; only {given[0]} is used and the rest are ignored",
        ))

    item_id = str(reference.get("item_id", "") or "").strip()
    family_id = str(reference.get("item_family", "") or "").strip()
    capability = str(reference.get("capability", "") or "").strip()
    if item_id and item_id not in item_ids:
        # Named, not just "a missing template": the entry path tells an author
        # where the reference is, and the value tells them what they typed.
        issues.append(ContentSetIssue(
            "error", str(path), f"{entry}.item_id references a missing item template: {item_id!r}",
        ))
    if family_id:
        if registry is None or not registry.family(family_id):
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{entry}.item_family '{family_id}' is not defined by this content set's contracts",
            ))
    if capability and registry is not None:
        known = any(
            capability in (family.get("capabilities") or [])
            for family in registry.item_families.values()
        )
        if not known:
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{entry}.capability '{capability}' is not declared by any item family in this "
                f"content set, so no item can satisfy it",
            ))

    for key in references.QUALITY_FLOOR_KEYS:
        if key not in reference:
            continue
        grade = reference[key]
        if isinstance(grade, bool) or not isinstance(grade, int) or grade < 0:
            issues.append(ContentSetIssue("error", str(path), f"{entry}.{key} must be a non-negative integer"))
    if quantity_field is not None and quantity_field in reference:
        value = reference[quantity_field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            issues.append(ContentSetIssue("error", str(path), f"{entry}.{quantity_field} must be a positive integer"))
    if "quality_penalty" in reference:
        penalty = reference["quality_penalty"]
        if isinstance(penalty, bool) or not isinstance(penalty, int) or penalty < 0:
            issues.append(ContentSetIssue("error", str(path), f"{entry}.quality_penalty must be a non-negative integer"))
    return issues


# Kept as the name the crafting validator and its callers already use.
_recipe_ingredient_issues = _item_reference_issues


def _validate_crafting_quality_contracts(
    content_root: Path,
    issues: list[ContentSetIssue],
    registry: Any = None,
) -> None:
    """Validate generic recipe metadata controlling material-grade outcomes."""
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    crafting_dir = content_root / "crafting"
    if not crafting_dir.is_dir():
        return
    for path in sorted(crafting_dir.glob("*.json")):
        payload = _load_json(path, issues, "crafting recipes")
        if not isinstance(payload, dict):
            continue
        for recipe_id, recipe in payload.items():
            if str(recipe_id).startswith("_"):
                continue
            if not isinstance(recipe, dict):
                issues.append(ContentSetIssue(
                    "error", str(path), f"recipe '{recipe_id}' must be an object",
                ))
                continue
            label = f"recipe '{recipe_id}'"

            # The recipe reader is strict, and it is the only reader of a recipe:
            # `Recipe` is where the engine decides what these fields mean, so
            # asking it is how this check stays in step with the engine instead
            # of listing the fields again and drifting. Every check below it
            # adds to that, not replaces it.
            from engine.crafting.recipe import Recipe
            from engine.utils.content_values import ContentValueError

            try:
                Recipe(str(recipe_id), recipe)
            except ContentValueError as refused:
                issues.append(ContentSetIssue("error", str(path), str(refused)))

            ingredients = recipe.get("ingredients", [])

            # `aliases` are alternative names a player might type, resolved by
            # engine/naming.py. A malformed entry would silently never match, so
            # validate the shape here rather than letting it fail quietly in play.
            if "aliases" in recipe:
                aliases = recipe["aliases"]
                if not isinstance(aliases, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.aliases must be an array"))
                else:
                    seen_aliases = set()
                    for alias_index, alias in enumerate(aliases):
                        alias_entry = f"{label}.aliases[{alias_index}]"
                        if isinstance(alias, bool) or not isinstance(alias, (str, int)):
                            issues.append(ContentSetIssue("error", str(path), f"{alias_entry} must be a string"))
                            continue
                        text = str(alias).strip()
                        if not text:
                            issues.append(ContentSetIssue("error", str(path), f"{alias_entry} must not be blank"))
                            continue
                        # Shorter than the resolver's minimum loose-match length
                        # means the alias can only ever match exactly.
                        if len(text) < 2:
                            issues.append(ContentSetIssue("warning", str(path), f"{alias_entry} is too short to match loosely: {text!r}"))
                        normalized = " ".join(text.replace("_", " ").replace("-", " ").lower().split())
                        if normalized in seen_aliases:
                            issues.append(ContentSetIssue("warning", str(path), f"{alias_entry} duplicates another alias: {text!r}"))
                        seen_aliases.add(normalized)

            if not isinstance(ingredients, list):
                issues.append(ContentSetIssue("error", str(path), f"{label}.ingredients must be an array"))
                continue
            quality_contributors = 0
            for index, ingredient in enumerate(ingredients):
                entry = f"{label}.ingredients[{index}]"
                issues.extend(_recipe_ingredient_issues(ingredient, entry, path, item_ids, registry))
                if not isinstance(ingredient, dict):
                    continue
                contributes = ingredient.get("quality_contributes", True)
                if not isinstance(contributes, bool):
                    issues.append(ContentSetIssue("error", str(path), f"{entry}.quality_contributes must be a boolean"))
                elif contributes:
                    quality_contributors += 1
                if "alternatives" in ingredient:
                    alternatives = ingredient["alternatives"]
                    if not isinstance(alternatives, list):
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.alternatives must be an array"))
                    else:
                        for alt_index, alternative in enumerate(alternatives):
                            alt_entry = f"{entry}.alternatives[{alt_index}]"
                            issues.extend(_recipe_ingredient_issues(alternative, alt_entry, path, item_ids, registry))
                            if not isinstance(alternative, dict):
                                continue
                            if "quality_penalty" in alternative:
                                penalty = alternative["quality_penalty"]
                                if isinstance(penalty, bool) or not isinstance(penalty, int) or penalty < 0:
                                    issues.append(ContentSetIssue("error", str(path), f"{alt_entry}.quality_penalty must be a non-negative integer"))
            tiers = recipe.get("quality_tiers", [])
            if not isinstance(tiers, list):
                continue
            requires_material_quality = any(
                isinstance(tier, dict)
                and isinstance(tier.get("min_material_quality"), int)
                and not isinstance(tier.get("min_material_quality"), bool)
                and int(tier["min_material_quality"]) > 0
                for tier in tiers
            )
            if requires_material_quality and quality_contributors == 0:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{label} requires material quality but has no quality-contributing ingredient",
                ))


def _validate_item_extension_data(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate optional generic item extension contracts used by the engine.

    Extension names describe mechanics, not a particular game theme: hosts may
    expose attachment slots and tokens may offer numeric modifiers.  Content
    remains free to author the actual slot and modifier names.
    """
    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, definition in payload.items():
            if not isinstance(definition, dict) or str(item_id).startswith("_"):
                continue
            properties = definition.get("properties", {})
            if not isinstance(properties, dict):
                continue
            label = f"item '{item_id}'"
            effect_type = properties.get("effect_type")
            if effect_type == "apply_effect":
                effect_data = properties.get("effect_data")
                if not isinstance(effect_data, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_data must be an object"))
                else:
                    effect_name = effect_data.get("name")
                    effect_kind = effect_data.get("type")
                    if not isinstance(effect_name, str) or not effect_name.strip():
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_data.name must be a non-empty string"))
                    if not isinstance(effect_kind, str) or not effect_kind.strip():
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_data.type must be a non-empty string"))
                    if "base_duration" in effect_data and (
                        isinstance(effect_data["base_duration"], bool)
                        or not isinstance(effect_data["base_duration"], (int, float))
                        or effect_data["base_duration"] <= 0
                    ):
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_data.base_duration must be a positive number"))
                    if effect_kind == "stat_mod":
                        modifiers = effect_data.get("modifiers")
                        if (
                            not isinstance(modifiers, dict)
                            or not modifiers
                            or any(
                                not isinstance(stat_name, str)
                                or not stat_name.strip()
                                or isinstance(amount, bool)
                                or not isinstance(amount, (int, float))
                                for stat_name, amount in modifiers.items()
                            )
                        ):
                            issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_data.modifiers must map stat names to numbers"))
            elif effect_type == "cleanse":
                effect_tags = properties.get("effect_tags")
                if (
                    not isinstance(effect_tags, list)
                    or not effect_tags
                    or any(not isinstance(tag, str) or not tag.strip() for tag in effect_tags)
                ):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.effect_tags must be a non-empty array of tags"))
            elif effect_type == "target_damage":
                damage_amount = properties.get("damage_amount")
                damage_type = properties.get("damage_type")
                if (
                    isinstance(damage_amount, bool)
                    or not isinstance(damage_amount, (int, float))
                    or damage_amount <= 0
                ):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.damage_amount must be a positive number"))
                if not isinstance(damage_type, str) or not damage_type.strip():
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.damage_type must be a non-empty string"))
            if "attachment_slots" in properties:
                slots = properties["attachment_slots"]
                if (
                    not isinstance(slots, list)
                    or not slots
                    or any(not isinstance(slot, str) or not slot.strip() for slot in slots)
                ):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment_slots must be a non-empty array of slot names"))
                elif len(set(slots)) != len(slots):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment_slots must not contain duplicates"))
            if "attachment" not in properties:
                continue
            attachment = properties["attachment"]
            if not isinstance(attachment, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment must be an object"))
                continue
            slot = attachment.get("slot")
            if not isinstance(slot, str) or not slot.strip():
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment.slot must be a non-empty string"))
            modifiers = attachment.get("modifiers")
            if not isinstance(modifiers, dict) or not modifiers:
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment.modifiers must be a non-empty object"))
                continue
            for modifier_name, value in modifiers.items():
                if modifier_name == "stats":
                    if not isinstance(value, dict) or not value or any(
                        isinstance(amount, bool) or not isinstance(amount, (int, float))
                        for amount in value.values()
                    ):
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment.modifiers.stats must map stat names to numbers"))
                elif isinstance(value, bool) or not isinstance(value, (int, float)):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.attachment.modifiers.{modifier_name} must be a number"))


def _resolve_manifest_path(content_set_path: Path | str) -> Path:
    """Return the manifest path for a package directory or manifest filename."""

    path = Path(content_set_path)
    return path / CONTENT_SET_MANIFEST_NAME if path.is_dir() else path


def load_content_set(
    content_set_path: Path | str,
    runtime_api: str = RUNTIME_API_VERSION,
) -> tuple[ContentSetDefinition | None, list[ContentSetIssue]]:
    """Load and validate one content set without starting a game runtime."""

    manifest_path = _resolve_manifest_path(content_set_path).resolve()
    issues: list[ContentSetIssue] = []
    payload = _load_json(manifest_path, issues, "content-set manifest")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(manifest_path), "content-set manifest must be a JSON object"))
        return None, issues

    package_root = manifest_path.parent
    required_strings = ("id", "title", "version", "manifest_schema_version", "engine_api_min", "engine_api_max")
    for key in required_strings:
        value = payload.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"missing/invalid string field '{key}'"))

    content_set_id = str(payload.get("id", "")).strip()
    if content_set_id and _CONTENT_SET_ID_PATTERN.fullmatch(content_set_id) is None:
        issues.append(ContentSetIssue("error", str(manifest_path), "id must match [a-z][a-z0-9_]*"))

    schema_version = str(payload.get("manifest_schema_version", "")).strip()
    if schema_version and schema_version != CONTENT_SET_SCHEMA_VERSION:
        issues.append(
            ContentSetIssue(
                "error",
                str(manifest_path),
                f"unsupported manifest_schema_version '{schema_version}', expected '{CONTENT_SET_SCHEMA_VERSION}'",
            )
        )

    minimum = str(payload.get("engine_api_min", "")).strip()
    maximum = str(payload.get("engine_api_max", "")).strip()
    lower = _parse_version(minimum)
    upper = _parse_version(maximum)
    if minimum and maximum:
        if lower is None or upper is None:
            issues.append(ContentSetIssue("error", str(manifest_path), "engine_api_min/max must be dotted numeric versions"))
        elif lower > upper:
            issues.append(ContentSetIssue("error", str(manifest_path), "engine_api_min must be <= engine_api_max"))
        elif not _runtime_in_range(runtime_api, minimum, maximum):
            issues.append(
                ContentSetIssue(
                    "error",
                    str(manifest_path),
                    f"runtime API {runtime_api} outside supported range {minimum}..{maximum}",
                )
            )

    paths = payload.get("paths")
    if not isinstance(paths, dict):
        issues.append(ContentSetIssue("error", str(manifest_path), "paths must be an object"))
        return None, issues

    resolved_paths: dict[str, Path] = {}
    for key in ("content_root", "ruleset", "presentation"):
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string"))
            continue
        resolved_paths[key] = (package_root / value).resolve()

    feature_profile_path: Path | None = None
    if "feature_profile" in paths:
        profile_value = paths.get("feature_profile")
        if not isinstance(profile_value, str) or profile_value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), "paths.feature_profile must be a non-empty string when provided"))
        else:
            feature_profile_path = (package_root / profile_value).resolve()
            profile_payload = _load_json(feature_profile_path, issues, "feature profile")
            if profile_payload is not None and not isinstance(profile_payload, dict):
                issues.append(ContentSetIssue("error", str(feature_profile_path), "feature profile must be a JSON object"))
    opening_path: Path | None = None
    opening_payload: dict[str, Any] = {}
    if "opening" in paths:
        opening_value = paths.get("opening")
        if not isinstance(opening_value, str) or opening_value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), "paths.opening must be a non-empty string when provided"))
        else:
            opening_path = (package_root / opening_value).resolve()
            raw_opening = _load_json(opening_path, issues, "opening scenario")
            if raw_opening is not None and not isinstance(raw_opening, dict):
                issues.append(ContentSetIssue("error", str(opening_path), "opening scenario must be a JSON object"))
            elif isinstance(raw_opening, dict):
                opening_payload = raw_opening

    content_root = resolved_paths.get("content_root")
    if content_root is not None:
        if not content_root.is_dir():
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.content_root does not resolve to a directory: {content_root}"))
        else:
            required_directories = list(_REQUIRED_DATA_DIRECTORIES)
            declared_capabilities = payload.get("capabilities")
            if isinstance(declared_capabilities, list) and "quests" in declared_capabilities:
                # Campaigns are currently a quest-progression implementation,
                # so their authored data belongs to the same optional system.
                required_directories.extend(("quests", "campaigns"))
            for directory in required_directories:
                if not (content_root / directory).is_dir():
                    issues.append(ContentSetIssue("error", str(content_root), f"missing required data directory '{directory}'"))

    ruleset_payload: dict[str, Any] = {}
    for key, label in (("ruleset", "ruleset"), ("presentation", "presentation")):
        target = resolved_paths.get(key)
        if target is None:
            continue
        nested_payload = _load_json(target, issues, label)
        if nested_payload is not None and not isinstance(nested_payload, dict):
            issues.append(ContentSetIssue("error", str(target), f"{label} must be a JSON object"))
        elif key == "ruleset" and isinstance(nested_payload, dict):
            ruleset_payload = nested_payload

    capabilities = payload.get("capabilities")
    capability_values: tuple[str, ...] = ()
    if not isinstance(capabilities, list):
        issues.append(ContentSetIssue("error", str(manifest_path), "capabilities must be an array"))
    else:
        normalized = [str(capability).strip() for capability in capabilities]
        if any(value == "" for value in normalized):
            issues.append(ContentSetIssue("error", str(manifest_path), "capabilities entries must be non-empty strings"))
        if len(set(normalized)) != len(normalized):
            issues.append(ContentSetIssue("error", str(manifest_path), "capabilities entries must be unique"))
        capability_values = tuple(normalized)

    start = payload.get("start")
    start_region_id = ""
    start_room_id = ""
    if not isinstance(start, dict):
        issues.append(ContentSetIssue("error", str(manifest_path), "start must be an object"))
    else:
        for key in ("scenario_id", "region_id", "room_id"):
            value = start.get(key)
            if not isinstance(value, str) or value.strip() == "":
                issues.append(ContentSetIssue("error", str(manifest_path), f"start.{key} must be a non-empty string"))
        start_region_id = str(start.get("region_id", "")).strip()
        start_room_id = str(start.get("room_id", "")).strip()

    if opening_path is not None and opening_payload:
        opening_scenario_id = str(opening_payload.get("scenario_id", "")).strip()
        if opening_scenario_id == "":
            issues.append(ContentSetIssue("error", str(opening_path), "opening scenario requires a non-empty 'scenario_id'"))
        elif start and opening_scenario_id != str(start.get("scenario_id", "")).strip():
            issues.append(ContentSetIssue("error", str(opening_path), "opening scenario_id must match start.scenario_id"))

    game_contract = _build_game_contract(capability_values, ruleset_payload, issues, resolved_paths.get("ruleset", manifest_path))

    if content_root is not None and content_root.is_dir() and start_region_id and start_room_id:
        region_path = content_root / "regions" / f"{start_region_id}.json"
        region_payload = _load_json(region_path, issues, "start region")
        if isinstance(region_payload, dict):
            rooms = region_payload.get("rooms")
            if not isinstance(rooms, dict) or start_room_id not in rooms:
                issues.append(
                    ContentSetIssue(
                        "error",
                        str(region_path),
                        f"start.room_id '{start_room_id}' does not exist in region '{start_region_id}'",
                    )
                )

        _validate_authored_world(content_root, start_region_id, start_room_id, issues)
        ruleset_source_path = resolved_paths.get("ruleset")
        if ruleset_source_path is not None:
            require_region_level_bands = _region_level_bands_required(
                ruleset_payload, issues, ruleset_source_path
            )
            require_region_hazard_coverage = _region_hazard_coverage_required(
                ruleset_payload, issues, ruleset_source_path
            )
            require_region_classification, region_biomes, region_types = _region_classification_policy(
                ruleset_payload, issues, ruleset_source_path
            )
            _validate_region_level_bands(
                content_root, issues, required=require_region_level_bands
            )
            _validate_region_classification(content_root, issues, required=require_region_classification, biomes=region_biomes, region_types=region_types)
            _validate_region_hazard_coverage(
                content_root, issues, required=require_region_hazard_coverage
            )
            _validate_ruleset_references(content_root, ruleset_payload, issues, ruleset_source_path)
            _validate_ambient_loot_references(content_root, ruleset_payload, issues, ruleset_source_path)
            _validate_advancement_content(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_starting_content(content_root, issues, ruleset_payload)
        _validate_skills_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_weather_profiles(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_contract_content(content_root, issues)
        _validate_dialogue_content(content_root, issues)
        _validate_quest_stages(content_root, issues)
        _validate_quest_choice_outcomes(content_root, issues)
        _validate_new_quest_objective_types(content_root, issues)
        _validate_collection_references(content_root, issues)
        _validate_discovery_references(content_root, issues)
        # One registry for every check that has to resolve a family or a
        # capability against the content set's own declarations, rather than one
        # parse per check.
        contract_registry = _load_contract_registry(content_root)
        _validate_vendor_orders(content_root, issues)
        _validate_resource_node_yields(content_root, issues)
        _validate_crafting_quality_contracts(content_root, issues, contract_registry)
        _validate_salvage_rules(
            content_root, issues, contract_registry,
            ruleset_path=resolved_paths.get("ruleset"),
            ruleset_payload=ruleset_payload,
        )
        _validate_item_salvage_outputs(content_root, issues, contract_registry)
        _validate_item_extension_data(content_root, issues)

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return (
        ContentSetDefinition(
            manifest_path=manifest_path,
            package_root=package_root,
            content_set_id=content_set_id,
            title=str(payload["title"]).strip(),
            version=str(payload["version"]).strip(),
            content_root=content_root,
            feature_profile_path=feature_profile_path,
            ruleset_path=resolved_paths["ruleset"],
            ruleset=ruleset_payload,
            presentation_path=resolved_paths["presentation"],
            opening_path=opening_path,
            opening=opening_payload,
            start_region_id=start_region_id,
            start_room_id=start_room_id,
            capabilities=capability_values,
            game_contract=game_contract,
        ),
        issues,
    )


def validate_content_set(content_set_path: Path, runtime_api: str = RUNTIME_API_VERSION) -> list[ContentSetIssue]:
    _definition, issues = load_content_set(content_set_path, runtime_api=runtime_api)
    return issues
