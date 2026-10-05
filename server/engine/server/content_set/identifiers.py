"""The ids a set defines (what every reference check looks names up in).

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
from .abilities import (_ability_ids)
from .advancement import (_player_stat_names, _ruleset_stat_names)
from .core import (ContentSetIssue, _load_json)
from .definitions import (_load_definition_ids)


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
    exit_refs: set[str] = set()
    room_refs: set[str] = set()
    npc_instance_ids: set[str] = set()
    regions_dir = content_root / "regions"
    if regions_dir.is_dir():
        for path in sorted(regions_dir.glob("*.json")):
            payload = _load_json(path, issues, "region definitions")
            if isinstance(payload, dict):
                region_id = payload.get("region_id")
                if isinstance(region_id, str) and region_id.strip():
                    region_ids.add(region_id)
                else:
                    region_id = path.stem
                    region_ids.add(region_id)
                rooms = payload.get("rooms")
                for room_id, room in (rooms.items() if isinstance(rooms, dict) else ()):
                    room_refs.add(f"{region_id}:{room_id}")
                    if isinstance(room, dict):
                        listed = room.get("exits") if isinstance(room.get("exits"), dict) else {}
                        hidden = (room.get("properties") or {}).get("hidden_exits") if isinstance(room.get("properties"), dict) else {}
                        for direction in list(listed) + list(hidden if isinstance(hidden, dict) else {}):
                            exit_refs.add(f"{region_id}:{room_id}:{direction}")
                    for placement in (room.get("initial_npcs") if isinstance(room, dict) else None) or ():
                        if isinstance(placement, dict) and isinstance(placement.get("instance_id"), str):
                            npc_instance_ids.add(placement["instance_id"])

    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    scene_ids: set[str] = set()
    scenes_dir = content_root / "scenes"
    if scenes_dir.is_dir():
        for path in sorted(scenes_dir.glob("*.json")):
            payload = _load_json(path, issues, "scenes")
            if isinstance(payload, dict):
                scene_ids |= {str(k) for k in payload if not str(k).startswith("_")}
    vehicle_ids: set[str] = set()
    vehicles_dir = content_root / "vehicles"
    if vehicles_dir.is_dir():
        for path in sorted(vehicles_dir.glob("*.json")):
            payload = _load_json(path, issues, "vehicles")
            if isinstance(payload, dict):
                vehicle_ids |= {str(k) for k in payload if not str(k).startswith("_")}
    return {
        "scenes": scene_ids,
        "vehicles": vehicle_ids,
        "items": item_ids,
        "recipes": recipe_ids,
        "quests": quest_ids,
        "campaigns": campaign_ids,
        "discoveries": discovery_ids,
        "regions": region_ids,
        "npcs": npc_ids,
        "spells": _ability_ids(content_root, issues),
        # The stats a character has. The engine defaults here; callers that hold the
        # ruleset add the ones it names (`_with_ruleset_stats`).
        "stats": _player_stat_names(),
        # `region:room` for every room, and the id of every placed NPC: what a
        # `spawn_npc` and a `remove_npc` may name.
        "rooms": room_refs,
        "exits": exit_refs,
        "npc_instances": npc_instance_ids,
    }


def _with_ruleset_stats(ids: dict[str, set[str]], ruleset_payload: Any) -> dict[str, set[str]]:
    ids["stats"] = ids["stats"] | _ruleset_stat_names(ruleset_payload if isinstance(ruleset_payload, dict) else {})
    return ids


# The condition kinds whose value names something the set defines: (kind, the field
# holding the id, the identifier bucket it must be found in).
_CONDITION_REFERENCES = _conditions.condition_references()

# The effects whose value names things the set defines: (effect, identifier bucket).

# Effects that give the character something. Paired with a `take_*` they make a
# service, and a service needs a guard (see `_check_effect_guards`).
_BENEFIT_EFFECTS = (
    "give_item", "give_gold", "give_rewards", "restore", "raise",
    "teach_spell", "grant_recipe", "grant_discovery",
)
