"""Constants, the issue and definition types, and the small readers every validator uses.

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
PRESENTATION_KEYS = ("presentation_id", "display_name", "theme_pack", "accessibility", "quest_text_pace")
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
    if "quest_text_pace" in payload:
        from engine.utils import pacing

        pace = payload["quest_text_pace"]
        if pace != "instant" and pacing.resolve_pace(pace) is None:
            issues.append(ContentSetIssue(
                "error", source,
                f"presentation.quest_text_pace {pace!r} is not a pace (\"instant\", a name -- {', '.join(pacing.TEXT_PACES)} -- "
                f"or characters per second from {pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})",
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


def _load_definitions(directory: Path) -> dict[str, dict]:
    """Every definition in a content directory by id (load errors are reported
    by the id pass that reads the same files)."""
    definitions: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, [], "definitions")
        if isinstance(payload, dict):
            definitions.update({
                str(key): value for key, value in payload.items()
                if isinstance(value, dict) and not str(key).startswith("_")
            })
    return definitions


# `ItemFactory.create_item_from_template` flattens a room placement's
# `properties_override` into the constructor's keywords; every item class takes
# `**kwargs`, so a key that is not a constructor field becomes an item property.
# Nothing refuses a value, so a wrong type is stored and fails where it is used
# (a string weight in an inventory's sum). A constructor field's type is its
# default's; these are the fields whose default is None, and the properties an
# item class reads without taking them as a field.
_ITEM_FIELD_KINDS_WHEN_NONE = {
    "key_id": "string", "target_id": "string", "linked_target_id": "string", "linked_action": "string",
    "equip_slot": "array", "contents": "array", "max_durability": "number", "weight": "number",
}
_ITEM_CLASS_READ_PROPERTIES = {"ResourceNode": {"respawn_days": "number"}}
_ITEM_FIXED_KEYS = ("type", "item_family", "obj_id", "id", "world", "properties")


def _item_field_kinds(item_type: str) -> dict[str, str]:
    """The constructor fields of the class `ITEM_CLASS_MAP` builds for `item_type`
    (plain `Item` for anything else), with the JSON type each one takes."""
    import inspect

    from engine.items.item_factory import ITEM_CLASS_MAP
    from engine.items.item import Item

    item_class = ITEM_CLASS_MAP.get(item_type, Item)
    kinds: dict[str, str] = {}
    for klass in (item_class, Item):
        for name, parameter in inspect.signature(klass.__init__).parameters.items():
            if name in ("self", "obj_id") or parameter.kind is parameter.VAR_KEYWORD or name in kinds:
                continue
            default = parameter.default
            kinds[name] = _ITEM_FIELD_KINDS_WHEN_NONE.get(name, "") if default is None else _json_kind(default)
    kinds.update(_ITEM_CLASS_READ_PROPERTIES.get(item_class.__name__, {}))
    return {name: kind for name, kind in kinds.items() if kind}


def _json_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"
