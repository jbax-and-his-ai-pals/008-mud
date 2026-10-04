"""Item reference issues, crafting quality contracts and item extension data.

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
from .advancement import (_CONTRACT_REGISTRY_CACHE)
from .core import (ContentSetIssue, _load_json)
from .definitions import (_load_definition_ids)
from .effects_conditions import (_check_effect_block)
from .identifiers import (_content_identifier_sets, _with_ruleset_stats)


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


def _validate_item_extension_data(
    content_root: Path, issues: list[ContentSetIssue], ruleset_payload: Any = None
) -> None:
    """Validate optional generic item extension contracts used by the engine.

    Extension names describe mechanics, not a particular game theme: hosts may
    expose attachment slots and tokens may offer numeric modifiers.  Content
    remains free to author the actual slot and modifier names.
    """
    from engine.items.consumable import CONSUMABLE_EFFECT_TYPES

    # Built once, on a scratch issue list: a malformed file is reported by whoever
    # first loaded it, not once more by every check that needs an id.
    ids: dict[str, set[str]] | None = None
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
            if effect_type is not None and effect_type not in CONSUMABLE_EFFECT_TYPES:
                # `use()` falls through to "You use the X." and spends it, so this
                # is a consumable that does nothing and is used up doing it. A
                # warning, not an error: it is a defect, but not one that stops a set
                # booting, and sets in the wild carry it (see chunk 7, item 2.3).
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"{label}.properties.effect_type {effect_type!r} is not an effect type a consumable "
                    f"executes (known: {', '.join(CONSUMABLE_EFFECT_TYPES)}), so it does nothing",
                ))
            if "effects" in properties and effect_type != "effects":
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"{label}.properties.effects is read only when effect_type is 'effects' "
                    f"(this item's is {effect_type!r}), so it is ignored",
                ))
            if effect_type == "effects":
                effects = properties.get("effects")
                if not isinstance(effects, dict) or not effects:
                    issues.append(ContentSetIssue(
                        "error", str(path), f"{label}.properties.effects must be a non-empty object of effects"
                    ))
                else:
                    if ids is None:
                        ids = _with_ruleset_stats(_content_identifier_sets(content_root, []), ruleset_payload)
                    _check_effect_block(effects, f"{label}.properties.effects", path, ids, content_root, issues)
            elif effect_type == "apply_effect":
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
