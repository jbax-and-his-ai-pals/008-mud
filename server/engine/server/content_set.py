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
_CAPABILITY_SYSTEMS = ("inventory", "dialogue", "combat", "magic", "crafting", "gathering", "quests", "collections", "discoveries", "social")
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
                elif "overrides" in npc and not isinstance(npc["overrides"], dict):
                    issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"room '{region_id}:{room_id}' initial NPC overrides must be an object"))
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
                item_id = order.get("item_id")
                if not isinstance(item_id, str) or item_id not in item_ids:
                    issues.append(ContentSetIssue("error", str(path), f"{entry}.item_id references a missing item template"))
                for field in ("quantity", "reward_gold"):
                    value = order.get(field)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (field == "quantity" and value < 1):
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.{field} must be a valid non-negative integer"))
                for field in ("repeatable", "crafted_only"):
                    if field in order and not isinstance(order[field], bool):
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.{field} must be a boolean"))
                if "min_material_quality_score" in order:
                    score = order["min_material_quality_score"]
                    if isinstance(score, bool) or not isinstance(score, int) or score < 0:
                        issues.append(ContentSetIssue("error", str(path), f"{entry}.min_material_quality_score must be a non-negative integer"))


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
        _validate_ruleset_references(content_root, ruleset_payload, issues, resolved_paths["ruleset"])
        _validate_ambient_loot_references(content_root, ruleset_payload, issues, resolved_paths["ruleset"])
        _validate_collection_references(content_root, issues)
        _validate_discovery_references(content_root, issues)
        _validate_vendor_orders(content_root, issues)
        _validate_resource_node_yields(content_root, issues)
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
