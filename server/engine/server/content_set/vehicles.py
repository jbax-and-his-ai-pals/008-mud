"""Vehicles (`data/vehicles/*.json`).

Part of the content-set validator package (`engine/server/content_set/`); see `__init__.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import ContentSetIssue, _load_json
from .identifiers import _content_identifier_sets


def _validate_vehicles(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`data/vehicles/*.json`: objects of vehicles keyed by id (`engine/world/vehicles.py`).

    A vehicle has a name, may start parked in a room that exists, and may be set down only in some biomes. An id
    names one vehicle across the set.
    """
    from engine.world.vehicles import VEHICLE_KEYS

    directory = content_root / "vehicles"
    if not directory.is_dir():
        return
    ids = _content_identifier_sets(content_root, [])
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, "vehicles")
        if payload is None:
            continue
        if not isinstance(payload, dict):
            issues.append(ContentSetIssue("error", str(path), "a vehicles file must be an object of vehicles keyed by id"))
            continue
        for vehicle_id, definition in payload.items():
            if str(vehicle_id).startswith("_"):
                continue
            label = f"vehicle '{vehicle_id}'"

            def error(message: str, label: str = label, path: Path = path) -> None:
                issues.append(ContentSetIssue("error", str(path), f"{label}{message}"))

            if vehicle_id in seen:
                error(f" is defined twice (also in {seen[vehicle_id]}); an id names one vehicle")
                continue
            seen[vehicle_id] = path.name
            if not isinstance(definition, dict):
                error(" must be an object")
                continue
            for key in definition:
                if key not in VEHICLE_KEYS:
                    error(f" has unknown key '{key}' (known: {', '.join(VEHICLE_KEYS)})")
            if not isinstance(definition.get("name"), str) or not definition["name"].strip():
                error(".name is required: how the game calls it (\"the skimmer\")")
            for key in ("description", "board_text", "disembark_text", "note"):
                if key in definition and not isinstance(definition[key], str):
                    error(f".{key} must be text")
            if "start" in definition:
                start = definition["start"]
                if not isinstance(start, dict) or set(start) != {"region", "room"}:
                    error(".start must be {region, room}: where it waits at the start")
                else:
                    known = ids.get("rooms") or set()
                    if known and f"{start['region']}:{start['room']}" not in known:
                        error(f".start names room '{start['region']}:{start['room']}', which this content set does not have")
            if "lands_in_biomes" in definition:
                biomes: Any = definition["lands_in_biomes"]
                if not isinstance(biomes, list) or not all(isinstance(b, str) and b.strip() for b in biomes):
                    error(".lands_in_biomes must be a list of biome names (omit it to land anywhere)")
