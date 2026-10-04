"""The authored world (rooms, exits, placements), patrol routes and faction rules.

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
from .core import (ContentSetIssue, _load_definitions, _load_json)
from .definitions import (_item_placement_override_issues, _load_definition_ids, _teleport_destinations)
from .npcs import (_npc_property_errors)


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
    item_templates: Optional[dict[str, dict]] = None

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
    # What an NPC can walk: `find_path` follows `room.exits` only, and a hidden
    # exit is not among them until something reveals it.
    walkable: dict[tuple[str, str], list[tuple[str, str]]] = {}
    patrol_placements: list[tuple[str, str, dict]] = []

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
            walkable[(region_id, room_id)] = list(neighbours)

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
                else:
                    patrol_placements.append((region_id, room_id, npc))
                if isinstance(npc, dict) and isinstance(npc.get("overrides"), dict) and npc.get("template_id") in npc_ids:
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
                    elif isinstance(overrides.get("properties_override"), dict):
                        room_refs = {f"{r}:{room}" for r, region_rooms in regions.items() for room in region_rooms}
                        for message in _npc_property_errors(overrides["properties_override"], f"room '{region_id}:{room_id}' {npc['template_id']} placement properties_override", room_refs):
                            issues.append(ContentSetIssue("error", str(region_paths[region_id]), message))
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
                    elif isinstance(item.get("properties_override"), dict):
                        if item_templates is None:
                            item_templates = _load_definitions(content_root / "items")
                        for severity, message in _item_placement_override_issues(
                            item["properties_override"], item_templates.get(item["item_id"], {}), item_ids,
                        ):
                            issues.append(ContentSetIssue(severity, str(region_paths[region_id]), f"room '{region_id}:{room_id}' item '{item['item_id']}' properties_override.{message}"))

    _validate_patrol_routes(content_root, regions, region_paths, walkable, patrol_placements, issues)

    reachable: set[tuple[str, str]] = set()
    pending = [(start_region_id, start_room_id)]
    # A story can carry the player somewhere (a `teleport` in a scene, a conversation or a trigger): where it
    # sets them down is a way in, and what can be walked to from there is reachable.
    pending.extend(_teleport_destinations(content_root))
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


def _validate_patrol_routes(
    content_root: Path,
    regions: dict[str, dict],
    region_paths: dict[str, Path],
    walkable: dict[tuple[str, str], list[tuple[str, str]]],
    placements: list[tuple[str, str, dict]],
    issues: list[ContentSetIssue],
) -> None:
    """A placed NPC's patrol, as `npcs/ai/movement.py::perform_patrol` walks it.

    The route is the template's `patrol_points` unless the placement overrides
    them, and each point is a room id in the NPC's *home* region -- the region
    it is placed in. A point that is not a room there, or that cannot be walked
    to (`find_path` follows visible exits only), silently turns the patrol into
    wandering; a `patrol_index` past the end raises in the AI tick; a patrol NPC
    with no points stands still; and points on an NPC whose behaviour is not
    `patrol` are never walked.
    """
    from collections import deque

    templates: dict[str, dict] = {}
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, [], "NPC definitions")
        if isinstance(payload, dict):
            templates.update({str(k): v for k, v in payload.items() if isinstance(v, dict) and not str(k).startswith("_")})

    def walk(start: tuple[str, str], goal: tuple[str, str]) -> bool:
        seen = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == goal:
                return True
            for neighbour in walkable.get(node, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return False

    for region_id, room_id, placement in placements:
        template_id = placement.get("template_id")
        template = templates.get(template_id)
        if template is None:
            continue
        overrides = placement.get("overrides") if isinstance(placement.get("overrides"), dict) else {}
        effective = {**template, **overrides}
        points = effective.get("patrol_points")
        source = "placement" if "patrol_points" in overrides else f"template '{template_id}'"
        label = f"room '{region_id}:{room_id}' {template_id} placement"

        def error(message: str) -> None:
            issues.append(ContentSetIssue("error", str(region_paths[region_id]), f"{label}: {message}"))

        behavior = effective.get("behavior_type")
        if behavior == "patrol" and (not isinstance(points, list) or not points):
            error("behavior_type is 'patrol' but it has no patrol_points, so it stands still")
            continue
        if not isinstance(points, list) or not points or not all(isinstance(p, str) and p.strip() for p in points):
            continue
        if behavior != "patrol":
            if "patrol_points" in overrides:
                error(f"patrol_points are walked only by a 'patrol' NPC; this one's behavior_type is {behavior!r}")
            continue
        index = effective.get("patrol_index", 0)
        if isinstance(index, int) and not isinstance(index, bool) and index >= len(points):
            error(f"patrol_index {index} is past the end of its {len(points)} patrol points (the AI tick raises)")
        missing = [p for p in points if p not in regions.get(region_id, {})]
        for point in missing:
            error(f"patrol point '{point}' (from the {source}) is not a room in region '{region_id}', where patrol points are resolved, so it wanders instead")
        if missing:
            continue
        legs = [((region_id, room_id), (region_id, points[0]))]
        legs += [((region_id, points[i]), (region_id, points[(i + 1) % len(points)])) for i in range(len(points))]
        for start, goal in legs:
            if start != goal and not walk(start, goal):
                error(f"patrol point '{goal[1]}' (from the {source}) cannot be walked to from '{start[1]}' by visible exits, so it wanders instead")
