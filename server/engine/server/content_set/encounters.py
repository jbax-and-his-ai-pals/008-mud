"""Encounter zones (`data/encounters/*.json`).

Part of the content-set validator package (`engine/server/content_set/`); see `__init__.py`.
"""

from __future__ import annotations

from pathlib import Path

from .core import ContentSetIssue, _load_json
from .identifiers import _content_identifier_sets


def _validate_encounters(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`data/encounters/*.json`: objects of zones keyed by id (`engine/world/encounters.py`).

    A zone names a region (and may name rooms of it), what may come (NPC templates that exist and are hostile-capable), and
    how likely it is on arriving. Everything it names must exist: a zone that names nothing real does nothing, silently.
    """
    from engine.world.encounters import ENCOUNTER_KEYS

    directory = content_root / "encounters"
    if not directory.is_dir():
        return
    ids = _content_identifier_sets(content_root, [])
    seen: dict[str, str] = {}

    def number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, "encounters")
        if payload is None:
            continue
        if not isinstance(payload, dict):
            issues.append(ContentSetIssue("error", str(path), "an encounters file must be an object of zones keyed by id"))
            continue
        for zone_id, definition in payload.items():
            if str(zone_id).startswith("_"):
                continue
            label = f"encounter zone '{zone_id}'"

            def error(message: str, label: str = label, path: Path = path) -> None:
                issues.append(ContentSetIssue("error", str(path), f"{label}{message}"))

            if zone_id in seen:
                error(f" is defined twice (also in {seen[zone_id]}); an id names one zone")
                continue
            seen[zone_id] = path.name
            if not isinstance(definition, dict):
                error(" must be an object")
                continue
            for key in definition:
                if key not in ENCOUNTER_KEYS:
                    error(f" has unknown key '{key}' (known: {', '.join(ENCOUNTER_KEYS)})")
            region = definition.get("region")
            rooms_known = ids.get("rooms") or set()
            regions_known = ids.get("regions") or set()
            if not isinstance(region, str) or not region.strip():
                error(".region is required: the region it covers")
            elif regions_known and region not in regions_known:
                error(f".region names '{region}', which this content set does not have")
            rooms = definition.get("rooms")
            if rooms is not None:
                if not isinstance(rooms, list) or not rooms or not all(isinstance(r, str) and r.strip() for r in rooms):
                    error(".rooms must be a non-empty list of room ids of that region (omit it to cover the whole region)")
                elif rooms_known and isinstance(region, str):
                    for room in rooms:
                        if f"{region}:{room}" not in rooms_known:
                            error(f".rooms names '{region}:{room}', which this content set does not have")
            monsters = definition.get("monsters")
            if not isinstance(monsters, list) or not monsters:
                error(".monsters is required: a list of NPC template ids, or {npc, weight}")
            else:
                for index, entry in enumerate(monsters):
                    npc_id = entry if isinstance(entry, str) else entry.get("npc") if isinstance(entry, dict) else None
                    if not isinstance(npc_id, str) or not npc_id.strip():
                        error(f".monsters[{index}] must be an NPC template id or {{\"npc\": id, \"weight\": n}}")
                        continue
                    if isinstance(entry, dict):
                        for key in entry:
                            if key not in ("npc", "weight"):
                                error(f".monsters[{index}].{key} is not read (known: npc, weight)")
                        if "weight" in entry and (not number(entry["weight"]) or entry["weight"] <= 0):
                            error(f".monsters[{index}].weight must be a number above 0")
                    if ids["npcs"] and npc_id not in ids["npcs"]:
                        error(f".monsters[{index}] names '{npc_id}', which is not an NPC template of this content set")
            chance = definition.get("chance")
            if chance is None:
                error(".chance is required: the chance (0 to 1) on arriving that something comes")
            elif not number(chance) or not 0 <= chance <= 1:
                error(".chance must be a number from 0 to 1")
            count = definition.get("count")
            if count is not None:
                whole = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 1  # noqa: E731
                ok = whole(count) or (isinstance(count, list) and len(count) == 2 and all(whole(v) for v in count) and count[0] <= count[1])
                if not ok:
                    error(".count must be a whole number of 1 or more, or [least, most]")
            cooldown = definition.get("cooldown")
            if cooldown is not None and (not number(cooldown) or cooldown < 0):
                error(".cooldown must be a number of seconds, 0 or more")
            for key in ("message", "note"):
                if key in definition and not isinstance(definition[key], str):
                    error(f".{key} must be text")
            message = definition.get("message")
            if isinstance(message, str):
                import string

                try:
                    fields = {f for _lit, f, _spec, _conv in string.Formatter().parse(message) if f}
                except ValueError as problem:
                    error(f".message is not a valid template ({problem})")
                    fields = set()
                for field in sorted(fields - {"name"}):
                    error(f".message uses {{{field}}}, which the engine does not fill (it offers {{name}})")
