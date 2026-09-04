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
_CAPABILITY_SYSTEMS = ("inventory", "dialogue", "combat", "magic", "crafting", "quests")
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
    if resolved["magic"]:
        status_fields.append("mana")
    ui_sections = ["log", "nearby", "status"]
    if resolved["inventory"]:
        ui_sections.append("inventory")
    if resolved["quests"]:
        ui_sections.append("quests")
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
    data_root: Path
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


def _validate_authored_world(
    data_root: Path,
    start_region_id: str,
    start_room_id: str,
    issues: list[ContentSetIssue],
) -> None:
    """Validate cross-file references that are only meaningful as a complete game."""
    regions: dict[str, dict[str, Any]] = {}
    region_paths: dict[str, Path] = {}
    for path in sorted((data_root / "regions").glob("*.json")):
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

    item_ids = _load_definition_ids(data_root / "items", "item definitions", issues)
    npc_ids = _load_definition_ids(data_root / "npcs", "NPC definitions", issues)
    reachable: set[tuple[str, str]] = set()
    pending = [(start_region_id, start_room_id)]

    for region_id, rooms in regions.items():
        for room_id, room in rooms.items():
            if not isinstance(room, dict):
                issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' must be an object"))
                continue
            exits = room.get("exits", {})
            if not isinstance(exits, dict):
                issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' exits must be an object"))
                continue
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
                    pending.append((target_region, target_room))

            for npc in room.get("initial_npcs", []):
                if not isinstance(npc, dict) or not isinstance(npc.get("template_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid initial_npcs entry"))
                elif npc["template_id"] not in npc_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing NPC template '{npc['template_id']}'"))
            for item in room.get("items", []):
                if not isinstance(item, dict) or not isinstance(item.get("item_id"), str):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' has an invalid items entry"))
                elif item["item_id"] not in item_ids:
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' references missing item '{item['item_id']}'"))

    while pending:
        location = pending.pop()
        if location in reachable:
            continue
        reachable.add(location)
        region_id, room_id = location
        room = regions.get(region_id, {}).get(room_id)
        if not isinstance(room, dict):
            continue
        exits = room.get("exits", {})
        if not isinstance(exits, dict):
            continue
        for destination in exits.values():
            if not isinstance(destination, str):
                continue
            target_region, separator, target_room = destination.partition(":")
            pending.append((target_region, target_room) if separator else (region_id, target_region))

    for region_id, rooms in regions.items():
        for room_id in rooms:
            if (region_id, room_id) not in reachable:
                issues.append(ContentSetIssue("warning", str(region_paths[region_id]), f"room '{region_id}:{room_id}' is not reachable from the declared start"))


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
    for key in ("data_root", "ruleset", "presentation"):
        value = paths.get(key)
        if not isinstance(value, str) or value.strip() == "":
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.{key} must be a non-empty string"))
            continue
        resolved_paths[key] = (package_root / value).resolve()

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

    data_root = resolved_paths.get("data_root")
    if data_root is not None:
        if not data_root.is_dir():
            issues.append(ContentSetIssue("error", str(manifest_path), f"paths.data_root does not resolve to a directory: {data_root}"))
        else:
            required_directories = list(_REQUIRED_DATA_DIRECTORIES)
            declared_capabilities = payload.get("capabilities")
            if isinstance(declared_capabilities, list) and "quests" in declared_capabilities:
                # Campaigns are currently a quest-progression implementation,
                # so their authored data belongs to the same optional system.
                required_directories.extend(("quests", "campaigns"))
            for directory in required_directories:
                if not (data_root / directory).is_dir():
                    issues.append(ContentSetIssue("error", str(data_root), f"missing required data directory '{directory}'"))

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

    if data_root is not None and data_root.is_dir() and start_region_id and start_room_id:
        region_path = data_root / "regions" / f"{start_region_id}.json"
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

        _validate_authored_world(data_root, start_region_id, start_room_id, issues)

    if any(issue.severity == "error" for issue in issues):
        return None, issues

    return (
        ContentSetDefinition(
            manifest_path=manifest_path,
            package_root=package_root,
            content_set_id=content_set_id,
            title=str(payload["title"]).strip(),
            version=str(payload["version"]).strip(),
            data_root=data_root,
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
