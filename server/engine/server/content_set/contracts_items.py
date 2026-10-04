"""Contract content, combat flavour, item envelopes, vendor orders, salvage, resource nodes, containers, stations.

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
from .item_references import (_item_reference_issues, _load_contract_registry)
from .references import (_format_placeholders)


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


FLAVOR_LINES = {"weakness": "a weakness", "resistance": "a resistance", "strong_resistance": "a resistance of 50 or more"}


def _validate_combat_flavor(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`combat/elements.json`'s `flavor_text`, and the retired `elemental_opposites`.

    config_combat.py replaces the engine's flavor table with the authored one,
    and magic/effects.py looks a hit's channel up there, falling back to the
    `default` entry by indexing it directly: a table without `default` raises
    on the first spell that finds a weakness or resistance in an unlisted
    channel. Each line is formatted with `target_name` only.

    `elemental_opposites` was loaded into a constant nothing read; it declared
    a mechanic the engine never had, so it is refused rather than kept inert.
    """
    path = content_root / "combat" / "elements.json"
    if not path.is_file():
        return
    payload = _load_json(path, [], "combat elements")
    if not isinstance(payload, dict):
        return

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(path), message))

    if "elemental_opposites" in payload:
        error("elemental_opposites is read by nothing (no mechanic uses it) and has been removed; delete it")
    if "flavor_text" not in payload:
        return
    flavor = payload["flavor_text"]
    if not isinstance(flavor, dict):
        error("flavor_text must be an object of damage channel -> lines")
        return
    channels = {str(value) for value in payload.get("valid_damage_types", [])} if isinstance(payload.get("valid_damage_types"), list) else set()
    if "default" not in flavor:
        error("flavor_text needs a `default` entry: a hit in a channel with no lines of its own looks it up and raises without one")
    for channel, lines in flavor.items():
        if str(channel).startswith("_"):
            continue
        label = f"flavor_text.{channel}"
        if channel != "default" and channels and channel not in channels:
            error(f"{label} is not a declared damage channel, so no hit ever uses it")
        if not isinstance(lines, dict):
            error(f"{label} must be an object of weakness / resistance / strong_resistance lines")
            continue
        for key, text in lines.items():
            if str(key).startswith("_"):
                continue
            if key not in FLAVOR_LINES:
                error(f"{label}.{key} is not a line the engine shows (known: {', '.join(FLAVOR_LINES)})")
            elif not isinstance(text, str):
                error(f"{label}.{key} must be text")
            else:
                try:
                    extra = sorted(_format_placeholders(text) - {"target_name"})
                except ValueError as problem:
                    error(f"{label}.{key} is not a valid message template ({problem})")
                    continue
                if extra:
                    error(f"{label}.{key} uses {', '.join('{' + name + '}' for name in extra)}; only {{target_name}} is filled")


def _validate_item_envelopes(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """What `definition_loader.load_item_templates` keeps and `ItemFactory` builds.

    The loader skips a template that is not an object or lacks a `name` or
    `type` key, counting it and saying nothing else, so every room, shop, loot
    table and quest naming it gets nothing. Past the loader, the class comes
    from the template's family (when its contract names one) and then from
    `type`; a class `ITEM_CLASS_MAP` does not have makes the factory return
    None for every instance. The data-integrity gate only warned about a
    missing name or type, and nothing checked the class.
    """
    from engine.contracts import ContractRegistry
    from engine.items.item_factory import ITEM_CLASS_MAP

    items_dir = content_root / "items"
    if not items_dir.is_dir():
        return
    registry = ContractRegistry.load(str(content_root))
    seen: dict[str, str] = {}
    for path in sorted(items_dir.glob("*.json")):
        if path.name in ("sets.json", "affixes.json"):
            continue
        payload = _load_json(path, [], "item definitions")
        if not isinstance(payload, dict):
            continue
        for item_id, template in payload.items():
            if str(item_id).startswith("_"):
                continue

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", str(path), f"item '{item_id}' {message}"))

            if not isinstance(template, dict):
                error("must be an object; the loader skips it")
                continue
            if item_id in seen:
                issues.append(ContentSetIssue("warning", str(path), f"item '{item_id}' is also defined in {seen[item_id]}; the file loaded last wins"))
            seen[item_id] = path.name
            name = template.get("name")
            if not isinstance(name, str) or not name.strip():
                error("needs a non-empty name; the loader skips a template without one" if "name" not in template else "name must be a non-empty string")
            if "type" not in template:
                error("needs a type; the loader skips a template without one, so everything that names it gets nothing")
                continue
            family_id = str(template.get("item_family", "") or "")
            family_class = registry.item_class_for_family(family_id) if family_id and not registry.is_empty else ""
            resolved = family_class or str(template.get("type") or "")
            if resolved not in ITEM_CLASS_MAP:
                source = f"item_family '{family_id}'" if family_class else "type"
                error(f"resolves to class {resolved!r} (from its {source}), which the item factory cannot build (known: {', '.join(sorted(ITEM_CLASS_MAP))})")
            if "description" in template and not isinstance(template["description"], str):
                error("description must be a string")
            for key in ("weight", "value"):
                value = template.get(key)
                if key in template and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                    error(f"{key} must be a number, 0 or more")
            if "stackable" in template and not isinstance(template["stackable"], bool):
                error("stackable must be a boolean")


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
