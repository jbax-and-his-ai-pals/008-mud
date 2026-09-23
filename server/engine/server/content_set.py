"""Runtime loading for versioned content-set packages.

The first contract supports a data root outside the package so that existing
world data can be wrapped and validated before it is migrated into a package.
"""

from __future__ import annotations

import json
import re
import string
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

# The manifest's shape, as module constants rather than literals inside the loader.
#
# The editor's create-set flow has to write a manifest this file accepts, and an
# editor that keeps its own copy of the rules is only safe while something checks
# the copy -- so these are the checked source. `toolkit/engine_vocabulary_dump.py`
# reads them and `mud-world-editor/tests/schema_parity_smoke.gd` compares the
# editor's table against it in both directions. `load_content_set` below reads
# them too, so there is one spelling of each rule rather than two.
REQUIRED_MANIFEST_STRINGS = ("id", "title", "version", "manifest_schema_version", "engine_api_min", "engine_api_max")
REQUIRED_MANIFEST_PATHS = ("content_root", "ruleset", "presentation")
OPTIONAL_MANIFEST_PATHS = ("feature_profile", "opening")
REQUIRED_START_FIELDS = ("scenario_id", "region_id", "room_id")
# The presentation file: which client theme pack a set asks for (sent to the
# client in `hello`), plus descriptive fields no runtime reads yet.
PRESENTATION_KEYS = ("presentation_id", "display_name", "theme_pack", "accessibility")
PRESENTATION_ACCESSIBILITY_KEYS = ("alt_text_required", "high_contrast_supported", "reduced_motion_supported")
_THEME_PACK_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
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
    presentation: dict[str, Any]
    opening_path: Path | None
    opening: dict[str, Any]
    start_region_id: str
    start_room_id: str
    capabilities: tuple[str, ...]
    game_contract: GameContract


def _validate_presentation(payload: dict[str, Any], path: Path, issues: list[ContentSetIssue]) -> bool:
    """A presentation file the client can act on. Returns whether it is usable.

    `theme_pack` is a client theme pack's `theme_id`, not a path: the client
    looks it up in its own catalog, so a path (as fantasy_frontier once wrote)
    or a name no client ships silently falls back to the default theme.
    Whether a pack of that id is installed is a client fact, checked for the
    shipped sets by test_presentation_theme_packs.py, not here.
    """
    before = len(issues)
    source = str(path)
    for key in payload:
        if not str(key).startswith("_") and key not in PRESENTATION_KEYS:
            issues.append(ContentSetIssue("error", source, f"presentation.{key} is not read (known: {', '.join(PRESENTATION_KEYS)})"))
    for key in ("presentation_id", "display_name"):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            issues.append(ContentSetIssue("error", source, f"presentation.{key} must be a non-empty string"))
    if "theme_pack" in payload:
        pack = payload["theme_pack"]
        if not isinstance(pack, str) or not _THEME_PACK_ID_PATTERN.fullmatch(pack):
            issues.append(ContentSetIssue(
                "error", source,
                f"presentation.theme_pack must be a client theme pack id such as 'fantasy_classic' (got {pack!r}); "
                "the client looks it up by id, not by path",
            ))
    accessibility = payload.get("accessibility")
    if accessibility is not None:
        if not isinstance(accessibility, dict):
            issues.append(ContentSetIssue("error", source, "presentation.accessibility must be an object"))
        else:
            for key, value in accessibility.items():
                if key not in PRESENTATION_ACCESSIBILITY_KEYS:
                    issues.append(ContentSetIssue("error", source, f"presentation.accessibility.{key} is not read (known: {', '.join(PRESENTATION_ACCESSIBILITY_KEYS)})"))
                elif not isinstance(value, bool):
                    issues.append(ContentSetIssue("error", source, f"presentation.accessibility.{key} must be true or false"))
    return len(issues) == before


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
                    "error", str(path),
                    f"{room_label} uses unknown hazard_type '{hazard_type}': no hazard of that "
                    f"name is declared in {elements_path.name}",
                ))
                continue
            authored_locations.setdefault(hazard_type, []).append(f"{region_id}:{room_id}")
            # Room-side numbers are *overrides* of the declared record, so they are
            # optional and only checked for being usable when present.
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
                    f"hazard '{hazard_type}' is declared but is not used by any room",
                ))


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

            # Room atmosphere is deliberately separate from `properties`: it
            # composes with district/region environment at read time.  A typo
            # here used to degrade silently ("dakr" simply never made a room
            # dark), so its small closed shape belongs in the same authored
            # world gate as exits and room placements.
            env_properties = room.get("env_properties")
            if env_properties is not None:
                if not isinstance(env_properties, dict):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' env_properties must be an object"))
                else:
                    bool_fields = ("dark", "outdoors", "has_windows", "noisy")
                    allowed_env_keys = {*bool_fields, "smell", "temperature"}
                    for key in env_properties:
                        if key not in allowed_env_keys:
                            issues.append(ContentSetIssue("warning", str(region_paths[region_id]), f"room '{region_id}:{room_id}' env_properties.{key} is ignored by the runtime"))
                    for key in bool_fields:
                        if key in env_properties and not isinstance(env_properties[key], bool):
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' env_properties.{key} must be a boolean"))
                    if "smell" in env_properties and not isinstance(env_properties["smell"], str):
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' env_properties.smell must be a string"))
                    if "temperature" in env_properties and env_properties["temperature"] not in ("normal", "cold", "hot"):
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' env_properties.temperature must be normal, cold, or hot"))

            time_descriptions = room.get("time_descriptions")
            if time_descriptions is not None:
                if not isinstance(time_descriptions, dict):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' time_descriptions must be an object"))
                else:
                    valid_periods = {"dawn", "day", "dusk", "night"}
                    for period, description in time_descriptions.items():
                        if period not in valid_periods:
                            issues.append(ContentSetIssue("warning", str(region_paths[region_id]), f"room '{region_id}:{room_id}' time_descriptions.{period} is ignored by the runtime"))
                        elif not isinstance(description, str):
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' time_descriptions.{period} must be a string"))

            adjacency[(region_id, room_id)] = neighbours

            for npc in room.get("initial_npcs", []):
                if not isinstance(npc, dict) or not isinstance(npc.get("template_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid initial_npcs entry"))
                elif npc["template_id"] not in npc_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing NPC template '{npc['template_id']}'"))
                elif "overrides" in npc and not isinstance(npc["overrides"], dict):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' initial NPC overrides must be an object"))
                elif isinstance(npc.get("overrides"), dict):
                    overrides = npc["overrides"]
                    allowed_override_keys = {
                        "name", "level", "health", "max_health", "mana", "max_mana", "behavior_type",
                        "properties_override", "patrol_points", "patrol_index",
                    }
                    for key in overrides:
                        if key not in allowed_override_keys:
                            issues.append(ContentSetIssue("warning", str(region_paths[region_id]), f"room '{region_id}:{room_id}' initial NPC override '{key}' is ignored by the runtime"))
                    if "name" in overrides and not isinstance(overrides["name"], str):
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' NPC override name must be a string"))
                    for key, minimum in (("level", 1), ("health", 1), ("max_health", 1), ("mana", 0), ("max_mana", 0), ("patrol_index", 0)):
                        if key in overrides:
                            value = overrides[key]
                            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                                issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' NPC override {key} must be an integer of at least {minimum}"))
                    if "properties_override" in overrides and not isinstance(overrides["properties_override"], dict):
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' NPC override properties_override must be an object"))
                    if "patrol_points" in overrides:
                        points = overrides["patrol_points"]
                        if not isinstance(points, list) or any(not isinstance(point, str) or not point.strip() for point in points):
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' NPC override patrol_points must be an array of room ids"))
                    if "behavior_type" in overrides:
                        from engine.config import NPC_BEHAVIOR_TYPES
                        behavior = overrides["behavior_type"]
                        if not isinstance(behavior, str) or behavior not in NPC_BEHAVIOR_TYPES:
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' NPC override behavior_type must be one of: {', '.join(NPC_BEHAVIOR_TYPES)}"))
            for item in room.get("items", []):
                if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid items entry"))
                elif item["item_id"] not in item_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing item '{item['item_id']}'"))
                else:
                    if "quantity" in item:
                        quantity = item["quantity"]
                        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' item '{item['item_id']}' quantity must be a positive integer"))
                    if "properties_override" in item and not isinstance(item["properties_override"], dict):
                        issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' item '{item['item_id']}' properties_override must be an object"))

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


def _validate_faction_rules(
    ruleset: Any,
    issues: list[ContentSetIssue],
    ruleset_path: Optional[Path] = None,
) -> None:
    """`ruleset.factions`: a set's own names for enemies, allies and bystanders.

    The engine's five factions and their attitudes have always been engine
    vocabulary, which is fine until a set wants to call its raiders something
    else -- and then two dozen call sites quietly stop working, because they used
    to ask the question by comparing the string `"hostile"`. The declaration is
    the fix; this is what refuses a malformed one, through the same `issues()`
    the reader uses, so the shape and its refusals cannot drift apart.
    """
    from engine.world import factions as faction_rules

    section = ruleset.get("factions") if isinstance(ruleset, dict) else None
    if section is None:
        return
    if not isinstance(section, dict):
        issues.append(ContentSetIssue(
            "error", str(ruleset_path or "ruleset"), "ruleset.factions must be an object"
        ))
        return

    for problem in faction_rules.issues(faction_rules.RulesetView({"factions": section})):
        issues.append(ContentSetIssue("error", str(ruleset_path or "ruleset"), problem))


def _validate_npc_vocabulary(
    content_root: Path,
    issues: list[ContentSetIssue],
    ruleset: Any = None,
) -> None:
    """The two engine-owned words an NPC template names: `faction`, `behavior_type`.

    Both are closed vocabularies, both are invisible from the content side, and a
    wrong value in either fails *quietly* and completely differently from what the
    author meant: an undeclared faction makes an NPC nobody can fight or talk to
    in the way they intended, and a misspelled `behavior_type` means no AI routine
    at all -- a guard who never moves and never reacts. Warnings, because both
    still load and run; the message names the consequence so the fix is obvious.
    """
    from engine.config import FACTION_DISPOSITIONS, NPC_BEHAVIOR_TYPES
    from engine.world import factions as faction_rules

    declared = faction_rules.dispositions(faction_rules.RulesetView(ruleset))
    known_behaviors = ", ".join(NPC_BEHAVIOR_TYPES)
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue
            behavior = template.get("behavior_type")
            if isinstance(behavior, str) and behavior.strip() and behavior.strip() not in NPC_BEHAVIOR_TYPES:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"NPC '{template_id}'.behavior_type '{behavior}' is not one of the engine's "
                    f"behaviours ({known_behaviors}); this NPC will stand still and do nothing",
                ))
            faction = template.get("faction")
            if not isinstance(faction, str) or not faction.strip():
                continue
            if faction.strip() not in declared:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"NPC '{template_id}'.faction '{faction}' is declared nowhere: not an engine "
                    f"faction, and not in this set's ruleset `factions`. It will be treated as a "
                    f"bystander -- no side, no attacks, no reputation. Declare it with a "
                    f"disposition (one of {', '.join(FACTION_DISPOSITIONS)}) to give it one",
                ))


_LOOT_ENTRY_KEYS = ("chance", "quantity", "is_chest")
_STOCK_ENTRY_KEYS = ("item_id", "price_multiplier", "relationship_min")
_GIFT_PREFERENCE_KEYS = ("preferred_item_ids", "preferred_categories", "preferred_gift_tags", "disliked_item_ids", "disliked_gift_tags")


def _validate_npc_trade_and_loot(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """An NPC's `loot_table`, vendor stock, tariff and gift preferences.

    Each reader skips what it cannot use: `NPC.die` drops nothing for an item id
    with no template and `random.randint` raises on a reversed quantity; vendor
    stock with a missing item is left off the list; a misspelt gift-preference
    key is never read, so the NPC simply has no preferences.
    """
    npc_dir = content_root / "npcs"
    if not npc_dir.is_dir():
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    campaign_ids = _knowledge_campaign_ids(content_root, issues)

    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for path in sorted(npc_dir.glob("*.json")):
        payload = _load_json(path, [], "NPC definitions")
        if not isinstance(payload, dict):
            continue
        source = str(path)
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", source, f"NPC '{template_id}'.{message}"))

            loot = template.get("loot_table")
            if loot is not None:
                if not isinstance(loot, dict):
                    error("loot_table must be an object of item id -> {chance, quantity}")
                    loot = {}
                for item_id, entry in loot.items():
                    label = f"loot_table.{item_id}"
                    if not isinstance(entry, dict):
                        error(f"{label} must be an object with chance and optional quantity")
                        continue
                    for key in entry:
                        if key not in _LOOT_ENTRY_KEYS:
                            error(f"{label}.{key} is not read (known: {', '.join(_LOOT_ENTRY_KEYS)})")
                    if item_id != "gold_value" and not entry.get("is_chest") and item_id not in item_ids:
                        error(f"{label} references missing item '{item_id}' (it is never dropped)")
                    chance = entry.get("chance", 0)
                    if not number(chance) or not 0 <= chance <= 1:
                        error(f"{label}.chance must be a number from 0 to 1")
                    if "quantity" in entry:
                        quantity = entry["quantity"]
                        low = 0 if item_id == "gold_value" else 1
                        if not (isinstance(quantity, list) and len(quantity) == 2
                                and all(isinstance(v, int) and not isinstance(v, bool) and v >= low for v in quantity)):
                            error(f"{label}.quantity must be [min, max], integers of at least {low}")
                        elif quantity[0] > quantity[1]:
                            error(f"{label}.quantity minimum ({quantity[0]}) is greater than its maximum ({quantity[1]})")
                    if "is_chest" in entry and not isinstance(entry["is_chest"], bool):
                        error(f"{label}.is_chest must be true or false")

            properties = template.get("properties")
            if not isinstance(properties, dict):
                continue
            stock = properties.get("sells_items")
            if stock is not None:
                if not isinstance(stock, list):
                    error("properties.sells_items must be an array of {item_id, price_multiplier}")
                    stock = []
                for index, entry in enumerate(stock):
                    label = f"properties.sells_items[{index}]"
                    if not isinstance(entry, dict):
                        error(f"{label} must be an object")
                        continue
                    for key in entry:
                        if key not in _STOCK_ENTRY_KEYS:
                            error(f"{label}.{key} is not read (known: {', '.join(_STOCK_ENTRY_KEYS)})")
                    if entry.get("item_id") not in item_ids:
                        error(f"{label}.item_id references missing item '{entry.get('item_id')}' (it is left off the list)")
                    if "price_multiplier" in entry and (not number(entry["price_multiplier"]) or entry["price_multiplier"] <= 0):
                        error(f"{label}.price_multiplier must be a positive number")
                    if "relationship_min" in entry and (not isinstance(entry["relationship_min"], int) or isinstance(entry["relationship_min"], bool) or not 0 <= entry["relationship_min"] <= 100):
                        error(f"{label}.relationship_min must be an integer from 0 to 100")
            if "sell_rate_multiplier" in properties and (not number(properties["sell_rate_multiplier"]) or properties["sell_rate_multiplier"] < 0):
                error("properties.sell_rate_multiplier must be a non-negative number")
            tariff = properties.get("tariff")
            if tariff is not None:
                if not isinstance(tariff, dict):
                    error("properties.tariff must be an object with campaign_id and rate")
                else:
                    if tariff.get("campaign_id") not in campaign_ids:
                        error(f"properties.tariff.campaign_id references missing campaign '{tariff.get('campaign_id')}' (the tariff never applies)")
                    if not number(tariff.get("rate")) or tariff.get("rate") < 0:
                        error("properties.tariff.rate must be a non-negative number")
            preferences = properties.get("gift_preferences")
            if preferences is not None:
                if not isinstance(preferences, dict):
                    error("properties.gift_preferences must be an object")
                    continue
                for key, values in preferences.items():
                    label = f"properties.gift_preferences.{key}"
                    if key not in _GIFT_PREFERENCE_KEYS:
                        error(f"{label} is not read (known: {', '.join(_GIFT_PREFERENCE_KEYS)})")
                        continue
                    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                        error(f"{label} must be an array of non-empty strings")
                        continue
                    if key.endswith("_item_ids"):
                        for value in values:
                            if value not in item_ids:
                                error(f"{label} references missing item '{value}'")


def _validate_npc_template_runtime_shapes(
    content_root: Path,
    issues: list[ContentSetIssue],
) -> None:
    """Refuse malformed NPC values the runtime otherwise silently normalises.

    The template editor writes these fields directly.  A bad probability makes an
    NPC act in ways its author cannot reason about, a missing inventory/spell
    reference disappears at load, and a malformed direct schedule can reach the
    movement loop as a half-entry.  Keeping the contract here gives every editor
    surface one honest answer before a world is started.

    This intentionally validates *direct* schedules only.  The separate
    ``ruleset.npc_schedules`` generator has a broader, setting-owned vocabulary
    and remains read-only until it has its own complete validator and editor.
    """
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    spell_ids = _ability_ids(content_root, issues)

    room_refs: set[str] = set()
    for region_path in sorted((content_root / "regions").glob("*.json")):
        region = _load_json(region_path, issues, "region definitions")
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("region_id", region_path.stem)).strip()
        rooms = region.get("rooms", {})
        if not region_id or not isinstance(rooms, dict):
            continue
        for room_id in rooms:
            if isinstance(room_id, str) and room_id.strip():
                room_refs.add(f"{region_id}:{room_id}")

    def number_in_range(value: Any, label: str, path: Path) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            issues.append(ContentSetIssue("error", str(path), f"{label} must be a number from 0 to 1"))

    def non_negative_integer(value: Any, label: str, path: Path) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            issues.append(ContentSetIssue("error", str(path), f"{label} must be a non-negative integer"))

    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for npc_id, template in payload.items():
            if str(npc_id).startswith("_") or not isinstance(template, dict):
                continue
            label = f"NPC '{npc_id}'"

            for field in ("friendly",):
                if field in template and not isinstance(template[field], bool):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be a boolean"))
            for field in ("level",):
                if field in template:
                    value = template[field]
                    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be an integer of at least 1"))
            for field in ("health", "max_mana", "attack_power", "defense"):
                if field in template:
                    value = template[field]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be a non-negative number"))

            properties = template.get("properties", {})
            if properties is not None and not isinstance(properties, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.properties must be an object"))
                properties = {}
            if isinstance(properties, dict):
                for field in ("aggression", "flee_threshold", "wander_chance", "spell_cast_chance"):
                    if field in properties:
                        number_in_range(properties[field], f"{label}.properties.{field}", path)
                if "move_cooldown" in properties:
                    non_negative_integer(properties["move_cooldown"], f"{label}.properties.move_cooldown", path)
                if "respawn_cooldown" in properties:
                    value = properties["respawn_cooldown"]
                    # Existing summoned/minion definitions use -1 as their explicit
                    # no-respawn sentinel.  It is a real engine convention, not a
                    # malformed duration, so preserve it while still refusing all
                    # other negative values.
                    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.respawn_cooldown must be an integer of -1 or greater"))
                for field in ("can_unlock_chests", "sells_houses"):
                    if field in properties and not isinstance(properties[field], bool):
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.{field} must be a boolean"))
                if "work_location" in properties:
                    work_location = properties["work_location"]
                    if not isinstance(work_location, str) or work_location not in room_refs:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{label}.properties.work_location must name an authored region:room",
                        ))

            if "patrol_points" in template:
                points = template["patrol_points"]
                if not isinstance(points, list) or any(not isinstance(point, str) or not point.strip() for point in points):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.patrol_points must be an array of non-empty room ids"))
            if "usable_spells" in template:
                spells = template["usable_spells"]
                if not isinstance(spells, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.usable_spells must be an array"))
                else:
                    for spell_id in spells:
                        if not isinstance(spell_id, str) or spell_id not in spell_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{label}.usable_spells references a missing ability: {spell_id!r}"))
            if "initial_inventory" in template:
                inventory = template["initial_inventory"]
                if not isinstance(inventory, list):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.initial_inventory must be an array"))
                else:
                    for index, entry in enumerate(inventory):
                        entry_label = f"{label}.initial_inventory[{index}]"
                        if not isinstance(entry, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                            continue
                        item_id = entry.get("item_id")
                        if not isinstance(item_id, str) or item_id not in item_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{entry_label}.item_id references a missing item template"))
                        if "quantity" in entry:
                            quantity = entry["quantity"]
                            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                                issues.append(ContentSetIssue("error", str(path), f"{entry_label}.quantity must be a positive integer"))

            if "schedule" not in template:
                continue
            schedule = template["schedule"]
            if not isinstance(schedule, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.schedule must be an object keyed by hour"))
                continue
            for hour, entry in schedule.items():
                try:
                    hour_number = int(hour)
                except (TypeError, ValueError):
                    hour_number = -1
                entry_label = f"{label}.schedule[{hour!r}]"
                if not 0 <= hour_number <= 23:
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must use an hour from 0 to 23"))
                if not isinstance(entry, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                    continue
                for field in ("region_id", "room_id", "activity"):
                    if field in entry and not isinstance(entry[field], str):
                        issues.append(ContentSetIssue("error", str(path), f"{entry_label}.{field} must be a string"))
                region_id = entry.get("region_id")
                room_id = entry.get("room_id")
                if isinstance(region_id, str) and isinstance(room_id, str) and f"{region_id}:{room_id}" not in room_refs:
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} names missing room '{region_id}:{room_id}'"))
                if "behavior_override" in entry and entry["behavior_override"] != "aggressive":
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{entry_label}.behavior_override must be 'aggressive' (the only override the scheduler reads)",
                    ))


_SIMPLE_RULESET_SECTION_KEYS = {
    "locksmithing": ("skill",),
    "economy": ("currency_name",),
    "calendar": ("day_names", "month_names", "start_time"),
    "spawning": ("no_spawn_keywords",),
    "elites": ("chance", "stat_multiplier", "loot_guaranteed_chance", "loot_quantity_multiplier", "name_pattern", "prefixes"),
    "player_defaults": ("player_class", "magic", "starting_inventory"),
    "npc_naming": ("first_names", "random_name_pattern"),
}


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
                    error(f"calendar.start_time.{key} must be an integer from 0 to {high} (otherwise the clock starts at midnight)")

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
                else:
                    error(f"{label} must be an item id or an object with item_id and quantity")
                    continue
                if item_id not in item_ids:
                    error(f"{label} references missing item '{item_id}' (the engine skips it and the player starts without it)")

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


def _validate_npc_schedule_rules(
    ruleset: Any,
    issues: list[ContentSetIssue],
    ruleset_path: Optional[Path] = None,
) -> None:
    """Validate the setting-owned grammar consumed by ``ai.schedules``.

    The scheduler deliberately has no fantasy vocabulary: content provides its
    own role names, template keywords, room categories, slots, and activities.
    That makes its *shape* especially important.  Before this gate, a misspelled
    slot or category quietly fell back to an NPC's home room, and a non-canonical
    hour such as ``"08"`` was never selected by the hourly reader.
    """
    if not isinstance(ruleset, dict) or "npc_schedules" not in ruleset:
        return
    section = ruleset["npc_schedules"]
    source = str(ruleset_path or "ruleset")
    if not isinstance(section, dict):
        issues.append(ContentSetIssue("error", source, "npc_schedules must be an object"))
        return

    excluded = section.get("excluded_name_keywords", [])
    if not isinstance(excluded, list) or any(not isinstance(value, str) or not value.strip() for value in excluded):
        issues.append(ContentSetIssue("error", source, "npc_schedules.excluded_name_keywords must be an array of non-empty strings"))

    categories = section.get("room_categories", {})
    if not isinstance(categories, dict):
        issues.append(ContentSetIssue("error", source, "npc_schedules.room_categories must be an object"))
        categories = {}
    else:
        for category_id, keywords in categories.items():
            label = f"npc_schedules.room_categories.{category_id}"
            if not isinstance(category_id, str) or not category_id.strip():
                issues.append(ContentSetIssue("error", source, "npc_schedules.room_categories needs non-empty category ids"))
            if not isinstance(keywords, list) or any(not isinstance(value, str) or not value.strip() for value in keywords):
                issues.append(ContentSetIssue("error", source, f"{label} must be an array of non-empty room-name keywords"))

    roles = section.get("roles", [])
    if not isinstance(roles, list):
        issues.append(ContentSetIssue("error", source, "npc_schedules.roles must be an array"))
        return
    seen_roles: set[str] = set()
    for index, role in enumerate(roles):
        role_label = f"npc_schedules.roles[{index}]"
        if not isinstance(role, dict):
            issues.append(ContentSetIssue("error", source, f"{role_label} must be an object"))
            continue
        role_id = role.get("id")
        if not isinstance(role_id, str) or not role_id.strip():
            issues.append(ContentSetIssue("error", source, f"{role_label}.id must be a non-empty string"))
        elif role_id in seen_roles:
            issues.append(ContentSetIssue("error", source, f"npc_schedules.roles repeats id '{role_id}'"))
        else:
            seen_roles.add(role_id)

        keywords = role.get("template_keywords", [])
        if not isinstance(keywords, list) or not keywords or any(not isinstance(value, str) or not value.strip() for value in keywords):
            issues.append(ContentSetIssue("error", source, f"{role_label}.template_keywords must be a non-empty array of strings"))

        slots = role.get("location_slots", {})
        if not isinstance(slots, dict) or not slots:
            issues.append(ContentSetIssue("error", source, f"{role_label}.location_slots must be a non-empty object"))
            slots = {}
        resolved_slots: set[str] = set()
        for slot_id, definition in slots.items():
            slot_label = f"{role_label}.location_slots.{slot_id}"
            if not isinstance(slot_id, str) or not slot_id.strip():
                issues.append(ContentSetIssue("error", source, f"{role_label}.location_slots needs non-empty slot ids"))
                continue
            if not isinstance(definition, dict):
                issues.append(ContentSetIssue("error", source, f"{slot_label} must be an object"))
                resolved_slots.add(slot_id)
                continue
            kind = definition.get("type", "self")
            if kind not in ("self", "property_or_self", "category"):
                issues.append(ContentSetIssue("error", source, f"{slot_label}.type must be self, property_or_self, or category"))
            if kind == "property_or_self":
                prop = definition.get("property")
                if not isinstance(prop, str) or not prop.strip():
                    issues.append(ContentSetIssue("error", source, f"{slot_label}.property must be a non-empty NPC property name"))
            if kind == "category":
                requested = definition.get("categories", [])
                if not isinstance(requested, list) or not requested or any(not isinstance(value, str) or not value.strip() for value in requested):
                    issues.append(ContentSetIssue("error", source, f"{slot_label}.categories must be a non-empty array of category ids"))
                elif isinstance(categories, dict):
                    for category_id in requested:
                        if category_id not in categories:
                            issues.append(ContentSetIssue("error", source, f"{slot_label}.categories names undeclared category '{category_id}'"))
                for relation in ("exclude", "fallback"):
                    if relation not in definition:
                        continue
                    target = definition[relation]
                    if not isinstance(target, str) or target not in resolved_slots:
                        issues.append(ContentSetIssue(
                            "error", source,
                            f"{slot_label}.{relation} must name an earlier location slot",
                        ))
            resolved_slots.add(slot_id)

        schedule = role.get("schedule", {})
        if not isinstance(schedule, dict) or not schedule:
            issues.append(ContentSetIssue("error", source, f"{role_label}.schedule must be a non-empty object keyed by hour"))
            continue
        for hour, entry in schedule.items():
            entry_label = f"{role_label}.schedule[{hour!r}]"
            try:
                hour_number = int(hour)
            except (TypeError, ValueError):
                hour_number = -1
            if not 0 <= hour_number <= 23 or str(hour) != str(hour_number):
                issues.append(ContentSetIssue("error", source, f"{entry_label} must use a canonical hour from 0 to 23"))
            if not isinstance(entry, dict):
                issues.append(ContentSetIssue("error", source, f"{entry_label} must be an object"))
                continue
            activity = entry.get("activity")
            if not isinstance(activity, str) or not activity.strip():
                issues.append(ContentSetIssue("error", source, f"{entry_label}.activity must be a non-empty string"))
            slot = entry.get("slot")
            if not isinstance(slot, str) or slot not in resolved_slots:
                issues.append(ContentSetIssue("error", source, f"{entry_label}.slot must name this role's location slot"))
            if "behavior_override" in entry and entry["behavior_override"] != "aggressive":
                issues.append(ContentSetIssue(
                    "error", source,
                    f"{entry_label}.behavior_override must be 'aggressive' (the only override the dispatcher reads)",
                ))


def _validate_social_rules(
    ruleset: Any,
    issues: list[ContentSetIssue],
    ruleset_path: Optional[Path] = None,
    content_root: Optional[Path] = None,
    capabilities: Any = None,
) -> None:
    """`ruleset.social`: the tiers a relationship passes through, and what a gift is worth.

    Until now nothing checked this section at all, and the failure mode was the
    quiet kind this project keeps meeting: a set that declares `tier` instead of
    `tiers`, or a `min` that is a string, silently falls back to the engine's
    defaults -- which are fantasy's tier names and a 15% discount -- and the author
    believes they configured something. So the keys are a closed vocabulary, the
    numbers are ranges the reader can honour, and the two things a *partial* set
    gets wrong are errors:

    * a tier set with no threshold at or below zero, which leaves every score
      under the lowest one wearing the engine's generic label;
    * two tiers at the same threshold, where one of them can never be reached.

    A set that declares nothing at all gets a **warning** rather than an error when
    it has any NPC in it: the engine then presents no bond surface at all -- gifts
    still change hands, but no score is kept, no tier is named and no vendor
    discount applies -- and the message says so, so keeping that is a choice rather
    than a surprise. **The capability and the section are one decision**: presenting
    the surface without a ladder is an error, and declaring a ladder nobody can see
    is an error too. `gift_tag_values` is open by design: its keys are item tags,
    which are content's.
    """
    social = ruleset.get("social") if isinstance(ruleset, dict) else None
    presents_surface = isinstance(capabilities, (list, tuple)) and "social" in capabilities
    if social is None:
        if presents_surface:
            # A *warning*, not an error: a scaffolded set inherits its source's
            # capability list before it has content for any of it, and that is a
            # legitimate first day. The engine degrades honestly (the commands say
            # this game tracks no bonds), and the author is told what to add.
            issues.append(ContentSetIssue(
                "warning", str(ruleset_path),
                "this set declares the `social` capability but no `social` section: bonds are "
                "presented with no ladder behind them, so `relationship` will report that this "
                "game tracks none. Declare `social.tiers`, or drop the capability from the manifest",
            ))
        elif content_root is not None and any((content_root / "npcs").glob("*.json")):
            issues.append(ContentSetIssue(
                "warning", str(ruleset_path),
                "no `social` section and no `social` capability: this set's NPCs have no bond "
                "surface. Gifts still change hands, but no score is kept, no tier is named and "
                "no vendor discount applies. Declare `social.tiers` and the capability to turn "
                "relationships on",
            ))
        return
    if capabilities is not None and not presents_surface:
        # The inverse stays an error: the ladder is authored and unreachable, which
        # is a declaration the engine ignores rather than a surface that says so.
        issues.append(ContentSetIssue(
            "error", str(ruleset_path),
            "this set declares a `social` ladder but not the `social` capability, so nobody can "
            "see or climb it. Add `social` to the manifest's capabilities, or drop the section",
        ))
    label_root = "social"
    if not isinstance(social, dict):
        issues.append(ContentSetIssue("error", str(ruleset_path), f"{label_root} must be an object"))
        return

    known = {"gift_values", "gift_tag_values", "tiers"}
    for key in sorted(social):
        if str(key).startswith("_") or key in known:
            continue
        issues.append(ContentSetIssue(
            "error", str(ruleset_path),
            f"{label_root}.{key} is not a field the engine reads (known: {', '.join(sorted(known))})",
        ))

    # The categories `use_give._gift_affinity` reads. A key outside this set is
    # never consulted, so it is a value an author set and no gift ever used.
    gift_categories = {
        "ordinary", "crafted", "preferred_item", "preferred_category",
        "preferred_tag", "disliked_item", "disliked_tag",
    }
    gift_values = social.get("gift_values")
    if gift_values is not None:
        if not isinstance(gift_values, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label_root}.gift_values must be an object"))
        else:
            for category in sorted(gift_values):
                if str(category).startswith("_"):
                    continue
                if category not in gift_categories:
                    issues.append(ContentSetIssue(
                        "error", str(ruleset_path),
                        f"{label_root}.gift_values.{category} is not a gift category the engine scores "
                        f"(known: {', '.join(sorted(gift_categories))})",
                    ))
                    continue
                value = gift_values[category]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    issues.append(ContentSetIssue(
                        "error", str(ruleset_path),
                        f"{label_root}.gift_values.{category} must be a number",
                    ))
    gift_tags = social.get("gift_tag_values")
    if gift_tags is not None:
        if not isinstance(gift_tags, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label_root}.gift_tag_values must be an object"))
        elif any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for key, value in gift_tags.items() if not str(key).startswith("_")
        ):
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label_root}.gift_tag_values must map an item tag to a number",
            ))

    tiers = social.get("tiers")
    if tiers is None:
        return
    if not isinstance(tiers, list):
        issues.append(ContentSetIssue("error", str(ruleset_path), f"{label_root}.tiers must be a list"))
        return
    thresholds: dict[int, int] = {}
    for index, tier in enumerate(tiers):
        label = f"{label_root}.tiers[{index}]"
        if not isinstance(tier, dict):
            issues.append(ContentSetIssue("error", str(ruleset_path), f"{label} must be an object"))
            continue
        minimum = tier.get("min")
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.min must be a whole number of relationship points, zero or more",
            ))
            continue
        if minimum in thresholds:
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.min repeats {minimum}, which tiers[{thresholds[minimum]}] already uses: "
                f"one of the two can never be reached",
            ))
        else:
            thresholds[minimum] = index
        tier_label = tier.get("label")
        if not isinstance(tier_label, str) or not tier_label.strip():
            issues.append(ContentSetIssue(
                "error", str(ruleset_path),
                f"{label}.label must be the name a player reads for this tier",
            ))
        discount = tier.get("vendor_discount")
        if discount is not None:
            if isinstance(discount, bool) or not isinstance(discount, (int, float)) or discount < 0:
                issues.append(ContentSetIssue(
                    "error", str(ruleset_path), f"{label}.vendor_discount must be a number, zero or more",
                ))
            elif discount > 0.95:
                # `relationship_discount` clamps to 0.95, so anything above it is a
                # number content wrote that the engine will quietly reduce.
                issues.append(ContentSetIssue(
                    "error", str(ruleset_path),
                    f"{label}.vendor_discount {discount} is above the 0.95 the engine will honour",
                ))

    if tiers and not any(minimum <= 0 for minimum in thresholds):
        issues.append(ContentSetIssue(
            "error", str(ruleset_path),
            f"{label_root}.tiers has no tier at or below zero relationship, so a stranger wears the "
            f"engine's own label instead of one this set chose",
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


def _knowledge_region_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    ids: set[str] = set()
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return ids
    for path in sorted(region_dir.glob("*.json")):
        payload = _load_json(path, issues, "region definitions")
        if isinstance(payload, dict) and not isinstance(payload.get("themes"), dict):
            ids.add(str(payload.get("region_id", path.stem)).strip())
    return ids


def _knowledge_campaign_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    ids: set[str] = set()
    campaign_dir = content_root / "campaigns"
    if not campaign_dir.is_dir():
        return ids
    for path in sorted(campaign_dir.glob("*.json")):
        payload = _load_json(path, issues, "campaign definitions")
        if isinstance(payload, dict):
            ids.add(str(payload.get("campaign_id", path.stem)).strip())
    return ids


def _validate_knowledge_topics(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`data/knowledge/topics.json` (`engine/core/knowledge_manager.py`).

    A topic's own condition language is not `engine/conditions.py`'s
    `KNOWN_KINDS` -- `KnowledgeManager._check_conditions` is a separate, hand-
    rolled vocabulary keyed on the NPC being asked (`region_id`, `faction`,
    `template_id`) and on player/world state (`knowledge_state`,
    `campaign_state`, `campaign_outcome`, `quest_state`), and a response's
    `conditions` object may combine several of them at once (every key present
    must hold, the same as the flat `and` the manager evaluates). `effects`
    reuses the dialogue effect language exactly, so it is checked the same way
    `_validate_dialogue_content` checks a choice's effects.
    """
    from engine.core.knowledge_manager import (
        CAMPAIGN_STATES, KNOWLEDGE_CONDITION_KINDS, KNOWLEDGE_STATES, QUEST_STATES,
    )

    from engine.dialogue.effects import KNOWN_EFFECTS

    path = content_root / "knowledge" / "topics.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "knowledge topics")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(path), "topics.json must be an object"))
        return

    topic_ids = {str(key) for key in payload if not str(key).startswith("_")}
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    region_ids = _knowledge_region_ids(content_root, issues)
    campaign_ids = _knowledge_campaign_ids(content_root, issues)

    common_topics = payload.get("__common_topics__")
    if common_topics is not None:
        if not isinstance(common_topics, list):
            issues.append(ContentSetIssue("error", str(path), "__common_topics__ must be an array"))
        else:
            for topic_id in common_topics:
                if not isinstance(topic_id, str) or topic_id not in topic_ids:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"__common_topics__ names '{topic_id}', which is not a topic this file declares",
                    ))

    for topic_id, topic in payload.items():
        if str(topic_id).startswith("_"):
            continue
        label = f"topic '{topic_id}'"
        if not isinstance(topic, dict):
            issues.append(ContentSetIssue("error", str(path), f"{label} must be an object"))
            continue
        if "display_name" in topic and not isinstance(topic["display_name"], str):
            issues.append(ContentSetIssue("error", str(path), f"{label}.display_name must be a string"))
        if "keywords" in topic:
            keywords = topic["keywords"]
            if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
                issues.append(ContentSetIssue("error", str(path), f"{label}.keywords must be an array of strings"))

        responses = topic.get("responses", [])
        if not isinstance(responses, list):
            issues.append(ContentSetIssue("error", str(path), f"{label}.responses must be an array"))
            continue
        for index, response in enumerate(responses):
            resp_label = f"{label}.responses[{index}]"
            if not isinstance(response, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label} must be an object"))
                continue
            if not isinstance(response.get("text"), str) or not response["text"].strip():
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.text must be a non-empty string"))
            if "priority" in response and (isinstance(response["priority"], bool) or not isinstance(response["priority"], int)):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.priority must be an integer"))

            conditions = response.get("conditions", {})
            if not isinstance(conditions, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.conditions must be an object"))
            else:
                for key, value in conditions.items():
                    cond_label = f"{resp_label}.conditions.{key}"
                    if key not in KNOWLEDGE_CONDITION_KINDS:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{cond_label} is not a condition this engine checks "
                            f"(known: {', '.join(KNOWLEDGE_CONDITION_KINDS)})",
                        ))
                    elif key in ("region_id", "faction", "template_id"):
                        if not isinstance(value, str) or not value.strip():
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be a non-empty string"))
                        elif key == "region_id" and region_ids and value not in region_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} references an unknown region '{value}'"))
                        elif key == "template_id" and npc_ids and value not in npc_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} references an unknown NPC template '{value}'"))
                    elif key == "knowledge_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            topic_ref = value.get("topic_id")
                            if not isinstance(topic_ref, str) or topic_ref not in topic_ids:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.topic_id must name a topic this file declares"))
                            if value.get("state") not in KNOWLEDGE_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(KNOWLEDGE_STATES)}"))
                    elif key == "campaign_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            campaign_ref = value.get("campaign_id")
                            if not isinstance(campaign_ref, str) or (campaign_ids and campaign_ref not in campaign_ids):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.campaign_id references an unknown campaign"))
                            if value.get("state") not in CAMPAIGN_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(CAMPAIGN_STATES)}"))
                    elif key == "campaign_outcome":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            campaign_ref = value.get("campaign_id")
                            if not isinstance(campaign_ref, str) or (campaign_ids and campaign_ref not in campaign_ids):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.campaign_id references an unknown campaign"))
                            if not isinstance(value.get("outcome"), str) or not value["outcome"].strip():
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.outcome must be a non-empty string"))
                    elif key == "quest_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            if value.get("state") not in QUEST_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(QUEST_STATES)}"))
                            if "from_this_npc" in value and not isinstance(value["from_this_npc"], bool):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.from_this_npc must be a boolean"))
                            if "id_pattern" in value and not isinstance(value["id_pattern"], str):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.id_pattern must be a string"))

            effects = response.get("effects", {})
            if not isinstance(effects, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.effects must be an object"))
            else:
                for key in sorted(effects):
                    if key not in KNOWN_EFFECTS:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{resp_label}.effects names '{key}', which is not an effect this engine knows "
                            f"(known: {', '.join(sorted(KNOWN_EFFECTS))})",
                        ))


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


_EXIT_REQUIREMENT_KEYS = {
    "skill": ("type", "skill_name", "difficulty", "failure_message"),
    "locked": ("type", "key_id", "pick_difficulty", "failure_message"),
}
_ENV_INTERACTION_KEYS = {
    "clear_exit_req": ("type", "direction", "duration", "message"),
    "suppress_hazard": ("type", "duration", "message"),
}


def _validate_room_passage_properties(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Room `properties.exit_requirements` and `properties.env_interactions`.

    Both fail open. `World.move_player` checks a requirement only when its type
    is `skill` or `locked` and only for a direction the room actually has, so a
    misspelt type or direction leaves the way free; a `skill` requirement whose
    name is misspelt as `skill` rolls against no skill at all. An interaction
    (`Room.apply_elemental_interaction`, fired by a spell's damage type) that
    clears a requirement the room does not have, or suppresses a hazard the room
    does not carry, does nothing.
    """
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    damage_types: set[str] = set()
    elements = _load_json(content_root / "combat" / "elements.json", [], "combat vocabulary") if (content_root / "combat" / "elements.json").is_file() else None
    if isinstance(elements, dict) and isinstance(elements.get("valid_damage_types"), list):
        damage_types = {str(value) for value in elements["valid_damage_types"]}

    def whole(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    for path in sorted(region_dir.glob("*.json")):
        region = _load_json(path, [], "region definitions")
        if not isinstance(region, dict) or isinstance(region.get("themes"), dict):
            continue
        region_id = str(region.get("region_id", path.stem))
        rooms = region.get("rooms", {})
        if not isinstance(rooms, dict):
            continue
        for room_id, room in rooms.items():
            if not isinstance(room, dict) or not isinstance(room.get("properties"), dict):
                continue
            properties = room["properties"]
            where = f"room '{region_id}:{room_id}'"
            source = str(path)

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", source, f"{where} {message}"))

            directions = set(room.get("exits", {}) or {}) if isinstance(room.get("exits"), dict) else set()
            hidden = properties.get("hidden_exits", {})
            if isinstance(hidden, dict):
                directions |= set(hidden)

            requirements = properties.get("exit_requirements")
            requirement_directions: set[str] = set()
            if requirements is not None:
                if not isinstance(requirements, dict):
                    error("properties.exit_requirements must be an object of direction -> requirement")
                    requirements = {}
                for direction, requirement in requirements.items():
                    label = f"properties.exit_requirements.{direction}"
                    requirement_directions.add(direction)
                    if direction not in directions:
                        error(f"{label} guards a direction the room has no exit for, so it never applies")
                    if not isinstance(requirement, dict):
                        error(f"{label} must be an object")
                        continue
                    kind = requirement.get("type")
                    if kind not in _EXIT_REQUIREMENT_KEYS:
                        error(f"{label}.type must be 'skill' or 'locked' (anything else leaves the way open)")
                        continue
                    for key in requirement:
                        if key not in _EXIT_REQUIREMENT_KEYS[kind]:
                            error(f"{label}.{key} is not read for a '{kind}' requirement (known: {', '.join(_EXIT_REQUIREMENT_KEYS[kind])})")
                    if "failure_message" in requirement and not isinstance(requirement["failure_message"], str):
                        error(f"{label}.failure_message must be a string")
                    if kind == "skill":
                        if not isinstance(requirement.get("skill_name"), str) or not requirement["skill_name"].strip():
                            error(f"{label}.skill_name is required for a skill requirement")
                        if "difficulty" in requirement and not whole(requirement["difficulty"]):
                            error(f"{label}.difficulty must be a non-negative integer")
                    else:
                        key_id = requirement.get("key_id")
                        if key_id is not None and key_id not in item_ids:
                            error(f"{label}.key_id references missing item '{key_id}'")
                        if "pick_difficulty" in requirement and not whole(requirement["pick_difficulty"]):
                            error(f"{label}.pick_difficulty must be a non-negative integer (over 100 means it cannot be picked)")

            interactions = properties.get("env_interactions")
            if interactions is None:
                continue
            if not isinstance(interactions, dict):
                error("properties.env_interactions must be an object of damage type -> reaction")
                continue
            for damage_type, reaction in interactions.items():
                label = f"properties.env_interactions.{damage_type}"
                if damage_types and damage_type not in damage_types:
                    error(f"{label} names a damage type combat/elements.json does not declare, so no spell triggers it")
                if not isinstance(reaction, dict):
                    error(f"{label} must be an object")
                    continue
                kind = reaction.get("type")
                if kind not in _ENV_INTERACTION_KEYS:
                    error(f"{label}.type must be 'clear_exit_req' or 'suppress_hazard'")
                    continue
                for key in reaction:
                    if key not in _ENV_INTERACTION_KEYS[kind]:
                        error(f"{label}.{key} is not read for '{kind}' (known: {', '.join(_ENV_INTERACTION_KEYS[kind])})")
                duration = reaction.get("duration", 10.0)
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                    error(f"{label}.duration must be a positive number of seconds")
                if "message" in reaction and not isinstance(reaction["message"], str):
                    error(f"{label}.message must be a string")
                if kind == "clear_exit_req" and reaction.get("direction") not in requirement_directions:
                    error(f"{label}.direction must name one of this room's exit_requirements, or the reaction does nothing")
                if kind == "suppress_hazard" and not properties.get("hazard_type"):
                    error(f"{label} suppresses a hazard, but the room has no hazard_type")


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


def _validate_instance_quests(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`quests/instances.json`: templates `QuestGenerator.generate_instance_quest` builds from.

    Every failure here was silent or a crash at generation time: a template with
    no target creatures or no existing entry region is never offered; an
    objective other than `clear_region` is accepted but never completes; and a
    reversed `min_rooms`/`max_rooms` or `target_count` range, or an empty room-name
    pool, raises inside `random` while the board is being filled.
    """
    path = content_root / "quests" / "instances.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "instance quest templates")
    if payload is None:
        return
    source = str(path)
    if not isinstance(payload, dict):
        issues.append(ContentSetIssue("error", source, "instances.json must be an object of instance quest templates"))
        return
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    region_ids = _knowledge_region_ids(content_root, issues)
    other_quest_ids: set[str] = set()
    for other in ("quests.json", "sagas.json"):
        other_payload = _load_json(content_root / "quests" / other, [], "quest definitions") if (content_root / "quests" / other).is_file() else None
        if isinstance(other_payload, dict):
            other_quest_ids |= {str(key) for key in other_payload if not str(key).startswith("_")}

    def positive_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 1

    def npc_ref(value: Any, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            issues.append(ContentSetIssue("error", source, f"{label} must be a non-empty string"))
        elif value not in npc_ids:
            issues.append(ContentSetIssue("error", source, f"{label} references missing NPC template '{value}'"))

    for template_id, template in payload.items():
        if str(template_id).startswith("_"):
            continue
        label = f"instance quest '{template_id}'"
        if not isinstance(template, dict):
            issues.append(ContentSetIssue("error", source, f"{label} must be an object"))
            continue
        if template_id in other_quest_ids:
            issues.append(ContentSetIssue(
                "error", source,
                f"{label} is also declared in quests.json or sagas.json; the loader keeps only one of them",
            ))
        if template.get("type") != "instance":
            issues.append(ContentSetIssue(
                "error", source,
                f"{label}.type must be 'instance' (only those are generated; other quests belong in quests.json)",
            ))
        if "level" in template and not positive_int(template["level"]):
            issues.append(ContentSetIssue("error", source, f"{label}.level must be an integer of at least 1"))
        if "giver_npc_template_id" in template:
            npc_ref(template["giver_npc_template_id"], f"{label}.giver_npc_template_id")

        if "possible_entry_regions" in template:
            regions = template["possible_entry_regions"]
            if not isinstance(regions, list) or not regions or any(not isinstance(r, str) or not r.strip() for r in regions):
                issues.append(ContentSetIssue("error", source, f"{label}.possible_entry_regions must be a non-empty array of region ids"))
            else:
                for region in regions:
                    if region_ids and region not in region_ids:
                        issues.append(ContentSetIssue("error", source, f"{label}.possible_entry_regions references missing region '{region}'"))

        rewards = template.get("rewards")
        if rewards is not None:
            if not isinstance(rewards, dict):
                issues.append(ContentSetIssue("error", source, f"{label}.rewards must be an object"))
            else:
                for key in ("xp", "gold"):
                    value = rewards.get(key)
                    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                        issues.append(ContentSetIssue("error", source, f"{label}.rewards.{key} must be a non-negative integer"))

        objective = template.get("objective")
        if not isinstance(objective, dict):
            issues.append(ContentSetIssue("error", source, f"{label}.objective must be an object"))
        else:
            if objective.get("type") != "clear_region":
                issues.append(ContentSetIssue(
                    "error", source,
                    f"{label}.objective.type must be 'clear_region' (the only instance objective the quest tracker completes)",
                ))
            targets = objective.get("possible_target_template_ids")
            if not isinstance(targets, list) or not targets:
                issues.append(ContentSetIssue(
                    "error", source,
                    f"{label}.objective.possible_target_template_ids must be a non-empty array; without one the template is never offered",
                ))
            else:
                for index, target in enumerate(targets):
                    npc_ref(target, f"{label}.objective.possible_target_template_ids[{index}]")
            if "completion_npc_template_id" in objective:
                npc_ref(objective["completion_npc_template_id"], f"{label}.objective.completion_npc_template_id")

        layout = template.get("layout_generation_config", {})
        if not isinstance(layout, dict):
            issues.append(ContentSetIssue("error", source, f"{label}.layout_generation_config must be an object"))
            continue
        layout_label = f"{label}.layout_generation_config"
        for key in ("region_name", "region_description"):
            if key in layout and (not isinstance(layout[key], str) or not layout[key].strip()):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.{key} must be a non-empty string"))
        min_rooms = layout.get("min_rooms", 3)
        max_rooms = layout.get("max_rooms", 7)
        if not positive_int(min_rooms) or not positive_int(max_rooms):
            issues.append(ContentSetIssue("error", source, f"{layout_label}.min_rooms and max_rooms must be integers of at least 1"))
        elif min_rooms > max_rooms:
            issues.append(ContentSetIssue("error", source, f"{layout_label}.min_rooms ({min_rooms}) is greater than max_rooms ({max_rooms})"))
        if "possible_room_names" in layout:
            names = layout["possible_room_names"]
            if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n.strip() for n in names):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.possible_room_names must be a non-empty array of strings"))
        if "target_count" in layout:
            count = layout["target_count"]
            if not (isinstance(count, list) and len(count) == 2 and all(positive_int(n) for n in count)):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.target_count must be [min, max], two integers of at least 1"))
            elif count[0] > count[1]:
                issues.append(ContentSetIssue("error", source, f"{layout_label}.target_count minimum ({count[0]}) is greater than its maximum ({count[1]})"))


FIELD_POLARITIES = ("positive", "neutral", "negative")
_FIELD_INTERACTION_KEYS = ("fallback_positive_suppresses_negative", "default_field_id", "polarities", "pairwise_rules")


def _validate_field_interactions(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`world/field_interactions.json` (`headless/field_fx.py::_load_field_interaction_config`).

    The loader forgives everything: an unreadable file, an unknown top-level
    key, a polarity outside the three it knows and a non-numeric coefficient are
    all dropped without a word, and an out-of-range coefficient is clamped. Keys
    are lower-cased on read, so a field id written any other way only works by
    accident. Its presence alone turns the ambient field system on.
    """
    path = content_root / "world" / "field_interactions.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "field interactions")
    if payload is None:
        return
    source = str(path)
    if not isinstance(payload, dict):
        issues.append(ContentSetIssue("error", source, "field_interactions.json must be an object"))
        return

    def field_id_ok(value: Any, label: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            issues.append(ContentSetIssue("error", source, f"{label} must be a non-empty field id"))
            return False
        if value != value.strip().lower():
            issues.append(ContentSetIssue("error", source, f"{label} '{value}' must be lower-case with no surrounding spaces (the engine reads it as '{value.strip().lower()}')"))
            return False
        return True

    def coefficient_ok(value: Any, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            issues.append(ContentSetIssue("error", source, f"{label} must be a number from 0 to 1"))

    for key in payload:
        if not str(key).startswith("_") and key not in _FIELD_INTERACTION_KEYS:
            issues.append(ContentSetIssue("error", source, f"'{key}' is not a field-interaction setting (known: {', '.join(_FIELD_INTERACTION_KEYS)})"))

    if "fallback_positive_suppresses_negative" in payload:
        coefficient_ok(payload["fallback_positive_suppresses_negative"], "fallback_positive_suppresses_negative")

    declared: set[str] = set()
    polarities = payload.get("polarities", {})
    if not isinstance(polarities, dict):
        issues.append(ContentSetIssue("error", source, "polarities must be an object of field id -> polarity"))
    else:
        for field_id, polarity in polarities.items():
            if field_id_ok(field_id, "polarities key"):
                declared.add(field_id)
            if polarity not in FIELD_POLARITIES:
                issues.append(ContentSetIssue("error", source, f"polarities.{field_id} must be one of {', '.join(FIELD_POLARITIES)}"))

    default_field_id = payload.get("default_field_id")
    if default_field_id is not None and field_id_ok(default_field_id, "default_field_id") and declared and default_field_id not in declared:
        issues.append(ContentSetIssue(
            "warning", source,
            f"default_field_id '{default_field_id}' has no declared polarity, so it is treated as neutral",
        ))

    rules = payload.get("pairwise_rules", {})
    if not isinstance(rules, dict):
        issues.append(ContentSetIssue("error", source, "pairwise_rules must be an object of source field -> {target field: coefficient}"))
        return
    for source_id, targets in rules.items():
        field_id_ok(source_id, "pairwise_rules key")
        if not isinstance(targets, dict) or not targets:
            issues.append(ContentSetIssue("error", source, f"pairwise_rules.{source_id} must be a non-empty object of target field -> coefficient"))
            continue
        for target_id, coefficient in targets.items():
            label = f"pairwise_rules.{source_id}.{target_id}"
            field_id_ok(target_id, f"pairwise_rules.{source_id} key")
            coefficient_ok(coefficient, label)
            if target_id == source_id:
                issues.append(ContentSetIssue("error", source, f"{label}: a field never suppresses itself, so this rule never applies"))
            for named in (source_id, target_id):
                if declared and named not in declared:
                    issues.append(ContentSetIssue("warning", source, f"{label} names '{named}', which has no declared polarity"))


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
            for field in ("tool_required",):
                if field in properties and not isinstance(properties[field], str):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.properties.{field} must be a string"))
            for field in ("charges", "max_charges", "respawn_days"):
                if field in properties:
                    value = properties[field]
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.{field} must be a non-negative integer"))
            for field in ("seasons", "weather_blocked_by"):
                if field in properties:
                    values = properties[field]
                    if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                        issues.append(ContentSetIssue("error", str(path), f"{label}.properties.{field} must be an array of non-empty strings"))
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


def _validate_container_templates(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate the authored contents and state of portable containers.

    `Container` hydrates `properties.contains` into real item instances. A bad
    entry otherwise disappears at runtime (or, before the quantity fix, quietly
    becomes one item), which is exactly the sort of content problem an author
    needs to see before playtesting.
    """
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, definition in payload.items():
            if not isinstance(definition, dict) or definition.get("type") != "Container":
                continue
            properties = definition.get("properties", {})
            if not isinstance(properties, dict):
                issues.append(ContentSetIssue("error", str(path), f"container '{item_id}'.properties must be an object"))
                continue
            label = f"container '{item_id}'.properties"
            if "capacity" in properties:
                capacity = properties["capacity"]
                if isinstance(capacity, bool) or not isinstance(capacity, (int, float)) or capacity < 0:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.capacity must be a non-negative number"))
            for field in ("locked", "is_open"):
                if field in properties and not isinstance(properties[field], bool):
                    issues.append(ContentSetIssue("error", str(path), f"{label}.{field} must be a boolean"))
            if properties.get("key_id") is not None:
                key_id = properties["key_id"]
                if not isinstance(key_id, str) or key_id not in item_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{label}.key_id references a missing item template"))
            if "contains" not in properties:
                continue
            contents = properties["contains"]
            if not isinstance(contents, list):
                issues.append(ContentSetIssue("error", str(path), f"{label}.contains must be an array"))
                continue
            for index, entry in enumerate(contents):
                entry_label = f"{label}.contains[{index}]"
                if not isinstance(entry, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label} must be an object"))
                    continue
                ref = entry.get("item_id")
                if not isinstance(ref, str) or ref not in item_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label}.item_id references a missing item template"))
                if "quantity" in entry:
                    quantity = entry["quantity"]
                    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
                        issues.append(ContentSetIssue("error", str(path), f"{entry_label}.quantity must be a positive integer"))
                if "properties_override" in entry and not isinstance(entry["properties_override"], dict):
                    issues.append(ContentSetIssue("error", str(path), f"{entry_label}.properties_override must be an object"))


def _validate_crafting_station_references(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A station-required recipe must name a station an item can actually provide."""
    station_types: set[str] = set()
    for path in sorted((content_root / "items").glob("*.json")):
        payload = _load_json(path, issues, "item definitions")
        if not isinstance(payload, dict):
            continue
        for definition in payload.values():
            if not isinstance(definition, dict):
                continue
            properties = definition.get("properties", {})
            if not isinstance(properties, dict):
                continue
            station = properties.get("crafting_station_type")
            if isinstance(station, str) and station.strip():
                station_types.add(station.strip())
    for path in sorted((content_root / "crafting").glob("*.json")):
        payload = _load_json(path, issues, "crafting recipes")
        if not isinstance(payload, dict):
            continue
        for recipe_id, recipe in payload.items():
            if not isinstance(recipe, dict) or str(recipe_id).startswith("_"):
                continue
            station = recipe.get("station_required")
            if station is None:
                continue
            if not isinstance(station, str):
                issues.append(ContentSetIssue("error", str(path), f"recipe '{recipe_id}'.station_required must be a string or null"))
            elif station.strip() not in station_types:
                issues.append(ContentSetIssue("error", str(path), f"recipe '{recipe_id}'.station_required names no authored crafting station: {station!r}"))


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
    for key in REQUIRED_MANIFEST_STRINGS:
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
    for key in REQUIRED_MANIFEST_PATHS:
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string"))
            continue
        resolved_paths[key] = (package_root / value).resolve()

    # Every optional path must be a non-empty string when it is named at all; what
    # each one *contains* is checked by its own branch below.
    for key in OPTIONAL_MANIFEST_PATHS:
        if key not in paths:
            continue
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string when provided"))

    feature_profile_path: Path | None = None
    profile_value = paths.get("feature_profile")
    if isinstance(profile_value, str) and profile_value.strip():
        feature_profile_path = (package_root / profile_value).resolve()
        profile_payload = _load_json(feature_profile_path, issues, "feature profile")
        if profile_payload is not None and not isinstance(profile_payload, dict):
            issues.append(ContentSetIssue("error", str(feature_profile_path), "feature profile must be a JSON object"))
    opening_path: Path | None = None
    opening_payload: dict[str, Any] = {}
    opening_value = paths.get("opening")
    if isinstance(opening_value, str) and opening_value.strip():
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
    presentation_payload: dict[str, Any] = {}
    for key, label in (("ruleset", "ruleset"), ("presentation", "presentation")):
        target = resolved_paths.get(key)
        if target is None:
            continue
        nested_payload = _load_json(target, issues, label)
        if nested_payload is not None and not isinstance(nested_payload, dict):
            issues.append(ContentSetIssue("error", str(target), f"{label} must be a JSON object"))
        elif key == "ruleset" and isinstance(nested_payload, dict):
            ruleset_payload = nested_payload
        elif key == "presentation" and isinstance(nested_payload, dict):
            if _validate_presentation(nested_payload, target, issues):
                presentation_payload = nested_payload

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
        # The vocabulary is the engine's, and until now it had no allowlist here:
        # `"craftting"` validated clean and enabled nothing at all, so a set could
        # be born with a system it never got. The world editor has always filtered
        # against this same list (and parity-checks its copy), which made the
        # editor stricter than the engine it is editing for.
        unknown = sorted(set(normalized) - set(_CAPABILITY_SYSTEMS))
        for capability in unknown:
            issues.append(ContentSetIssue(
                "error", str(manifest_path),
                f"capabilities names '{capability}', which is not an engine capability "
                f"(known: {', '.join(_CAPABILITY_SYSTEMS)}) -- it would enable nothing",
            ))
        capability_values = tuple(normalized)

    start = payload.get("start")
    start_region_id = ""
    start_room_id = ""
    if not isinstance(start, dict):
        issues.append(ContentSetIssue("error", str(manifest_path), "start must be an object"))
    else:
        for key in REQUIRED_START_FIELDS:
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
        _validate_district_contiguity(content_root, issues)
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
            _validate_district_coverage_policy(ruleset_payload, issues, ruleset_source_path)
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
        _validate_social_rules(ruleset_payload, issues, ruleset_source_path, content_root, capability_values)
        _validate_faction_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_npc_vocabulary(content_root, issues, ruleset_payload)
        _validate_npc_template_runtime_shapes(content_root, issues)
        _validate_npc_trade_and_loot(content_root, issues)
        _validate_npc_schedule_rules(ruleset_payload, issues, ruleset_source_path)
        _validate_weather_profiles(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_simple_ruleset_sections(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_crime_and_debug_rules(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_dynamic_themes(content_root, ruleset_payload, issues, ruleset_source_path)
        _validate_contract_content(content_root, issues)
        _validate_dialogue_content(content_root, issues)
        _validate_knowledge_topics(content_root, issues)
        _validate_room_passage_properties(content_root, issues)
        _validate_quest_stages(content_root, issues)
        _validate_instance_quests(content_root, issues)
        _validate_field_interactions(content_root, issues)
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
        _validate_container_templates(content_root, issues)
        _validate_crafting_station_references(content_root, issues)
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
            presentation=presentation_payload,
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
