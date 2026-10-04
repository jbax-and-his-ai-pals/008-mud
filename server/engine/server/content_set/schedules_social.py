"""NPC schedules and the social (relationship) rules.

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
from .core import (ContentSetIssue)


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
