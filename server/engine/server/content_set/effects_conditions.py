"""Condition trees and effect blocks (known kinds, shapes, referenced ids) and room passages.

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
from .abilities import (_condition_issues)
from .core import (ContentSetIssue, _load_json)
from .definitions import (_load_definition_ids)
from .identifiers import (_BENEFIT_EFFECTS, _CONDITION_REFERENCES, _content_identifier_sets)


def _condition_leaves(node: Any):
    """Every leaf condition in a tree, descending through `all`, `any`, `not` and lists."""
    if isinstance(node, list):
        for child in node:
            yield from _condition_leaves(child)
        return
    if not isinstance(node, dict):
        return
    for composite in ("all", "any"):
        if composite in node:
            yield from _condition_leaves(node[composite])
            return
    if "not" in node:
        yield from _condition_leaves(node["not"])
        return
    yield node


def _check_condition(
    node: Any, where: str, path: Path, ids: dict[str, set[str]], issues: list[ContentSetIssue]
) -> None:
    """A condition tree must use known kinds, and every id in it, at any depth, must exist.

    The id check used to look at the top node only, so a `has_item` nested under
    `all`, `any` or `not` -- how a real gate is written -- was never checked
    against the items the set defines.
    """
    issues.extend(_condition_issues(node, where, path))
    for leaf in _condition_leaves(node):
        kind = str(leaf.get("kind", ""))
        if kind in ("room_clear", "npc_present"):
            given = [key for key in ("region_id", "room_id") if str(leaf.get(key, "") or "").strip()]
            if len(given) == 1:
                issues.append(ContentSetIssue(
                    "error", str(path), f"{where} {kind} needs region_id and room_id together, or neither"
                ))
            else:
                _check_room_reference(leaf.get("region_id"), leaf.get("room_id"), f"{where} {kind}", path, ids, issues)
        for reference_kind, key, bucket in _CONDITION_REFERENCES:
            if kind != reference_kind:
                continue
            identifier = str(leaf.get(key, "") or "").strip()
            if identifier and ids[bucket] and identifier not in ids[bucket]:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{where} names {key} '{identifier}', which is not defined in this content set",
                ))


def _check_effect_block(
    block: Any, where: str, path: Path, ids: dict[str, set[str]], content_root: Path,
    issues: list[ContentSetIssue],
) -> None:
    """An effects mapping: known effects, values of the right shape, ids that exist."""
    from engine.dialogue.effects import KNOWN_EFFECTS, effect_references, effect_shape_issues

    if not isinstance(block, dict):
        return
    for key in sorted(block):
        if key not in KNOWN_EFFECTS:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} has unknown effect '{key}' "
                f"(known: {', '.join(sorted(KNOWN_EFFECTS))})",
            ))
    for problem in effect_shape_issues(block):
        issues.append(ContentSetIssue("error", str(path), f"{where}: {problem}"))
    for key, bucket in effect_references():
        if key not in block:
            continue
        for identifier in _effect_identifiers(block[key]):
            if ids[bucket] and identifier not in ids[bucket]:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{where} effect {key} names '{identifier}', "
                    f"which is not defined in this content set",
                ))
    scene = block.get("play_scene")
    if isinstance(scene, str) and scene.strip() and scene.strip() not in ids["scenes"]:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{where} effect play_scene names scene '{scene}', which is not in data/scenes of this content set",
        ))
    rewards = block.get("give_rewards")
    if isinstance(rewards, dict):
        for identifier in _effect_identifiers(rewards.get("items")):
            if ids["items"] and identifier not in ids["items"]:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{where} effect give_rewards names item '{identifier}', "
                    f"which is not defined in this content set",
                ))
    relationship = block.get("adjust_relationship")
    if isinstance(relationship, dict):
        npc_id = str(relationship.get("npc", "") or "").strip()
        if npc_id and ids["npcs"] and npc_id not in ids["npcs"]:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect adjust_relationship names NPC '{npc_id}', "
                f"which is not defined in this content set",
            ))
    move = block.get("move_npc")
    if isinstance(move, dict):
        npc_id = str(move.get("npc", "") or "").strip()
        region_id = str(move.get("region", "") or "").strip()
        if npc_id and ids["npcs"] and npc_id not in ids["npcs"]:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect move_npc names NPC '{npc_id}', "
                f"which is not defined in this content set",
            ))
        if region_id and ids["regions"] and region_id not in ids["regions"]:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect move_npc names region '{region_id}', "
                f"which is not defined in this content set",
            ))
    reveal = block.get("reveal_exit")
    if isinstance(reveal, dict):
        _check_reveal_exit(reveal, where, content_root, path, issues)
    spawn = block.get("spawn_npc")
    if isinstance(spawn, dict):
        npc_id = str(spawn.get("npc", "") or "").strip()
        if npc_id and ids["npcs"] and npc_id not in ids["npcs"]:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect spawn_npc names NPC '{npc_id}', which is not defined in this content set",
            ))
        _check_room_reference(spawn.get("region"), spawn.get("room"), f"{where} effect spawn_npc", path, ids, issues)
    seal = block.get("seal_exit")
    if isinstance(seal, dict):
        _check_room_reference(seal.get("region"), seal.get("room"), f"{where} effect seal_exit", path, ids, issues)
        region_id, room_id = str(seal.get("region", "") or "").strip(), str(seal.get("room", "") or "").strip()
        direction = str(seal.get("direction", "") or "").strip().lower()
        if region_id and room_id and direction and f"{region_id}:{room_id}" in ids["rooms"] \
                and f"{region_id}:{room_id}:{direction}" not in ids["exits"]:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect seal_exit names direction '{direction}', which room '{region_id}:{room_id}' does not have",
            ))
    pupil = block.get("teach_companion")
    if isinstance(pupil, dict):
        if ids["npcs"] and str(pupil.get("npc", "") or "").strip() not in ids["npcs"]:
            issues.append(ContentSetIssue("error", str(path), f"{where} effect teach_companion names npc '{pupil.get('npc')}', which is not defined in this content set"))
        if ids["spells"] and str(pupil.get("spell", "") or "").strip() not in ids["spells"]:
            issues.append(ContentSetIssue("error", str(path), f"{where} effect teach_companion names ability '{pupil.get('spell')}', which is not defined in this content set"))
    turncoat = block.get("set_faction")
    if isinstance(turncoat, dict):
        known = ids["npcs"] | ids["npc_instances"]
        if known and str(turncoat.get("npc", "") or "").strip() not in known:
            issues.append(ContentSetIssue("error", str(path), f"{where} effect set_faction names npc '{turncoat.get('npc')}', which is not defined in this content set"))
    parked = block.get("place_vehicle")
    if isinstance(parked, dict):
        if str(parked.get("vehicle", "") or "").strip() not in ids["vehicles"]:
            issues.append(ContentSetIssue("error", str(path), f"{where} effect place_vehicle names vehicle '{parked.get('vehicle')}', which is not in data/vehicles of this content set"))
        _check_room_reference(parked.get("region"), parked.get("room"), f"{where} effect place_vehicle", path, ids, issues)
    rise = block.get("set_respawn")
    if isinstance(rise, dict):
        _check_room_reference(rise.get("region"), rise.get("room"), f"{where} effect set_respawn", path, ids, issues)
    warp = block.get("teleport")
    if isinstance(warp, dict):
        _check_room_reference(warp.get("region"), warp.get("room"), f"{where} effect teleport", path, ids, issues)
    removal = block.get("remove_npc")
    if removal is not None:
        target = removal.get("npc") if isinstance(removal, dict) else removal
        target = str(target or "").strip()
        known = ids["npcs"] | ids["npc_instances"]
        if target and known and target not in known:
            issues.append(ContentSetIssue(
                "error", str(path),
                f"{where} effect remove_npc names '{target}', which is neither an NPC template nor a placed "
                f"NPC in this content set",
            ))
        if isinstance(removal, dict):
            _check_room_reference(removal.get("region"), removal.get("room"), f"{where} effect remove_npc", path, ids, issues)
    raised = block.get("raise")
    if isinstance(raised, dict) and isinstance(raised.get("stats"), dict):
        for stat in sorted(str(name) for name in raised["stats"]):
            if ids["stats"] and stat not in ids["stats"]:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{where} effect raise names stat '{stat}', which is not a stat this character has "
                    f"(stats: {', '.join(sorted(ids['stats']))})",
                ))


def _check_room_reference(
    region: Any, room: Any, where: str, path: Path, ids: dict[str, set[str]], issues: list[ContentSetIssue]
) -> None:
    """A region and room an effect names must be ones this set defines (both or neither)."""
    region_id = str(region or "").strip()
    room_id = str(room or "").strip()
    if not region_id or not room_id or not ids["rooms"]:
        return  # a missing half is `effect_shape_issues`'s to report
    if region_id not in ids["regions"]:
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} names region '{region_id}', which is not defined in this content set"
        ))
    elif f"{region_id}:{room_id}" not in ids["rooms"]:
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} names room '{room_id}', which region '{region_id}' does not have"
        ))


def _guaranteed_leaves(node: Any, negated: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The leaf conditions a tree guarantees: `(must hold, must not hold)`.

    `all` guarantees every child, and so does a negated `any` (not a and not b);
    `any` and a negated `all` guarantee none. A bare list reads as `all`, as it does
    in `_condition_issues`.
    """
    if isinstance(node, list):
        children, conjunctive = node, not negated
    elif isinstance(node, dict):
        if "all" in node:
            children, conjunctive = node["all"], not negated
        elif "any" in node:
            children, conjunctive = node["any"], negated
        elif "not" in node:
            return _guaranteed_leaves(node["not"], not negated)
        else:
            return ([], [node]) if negated else ([node], [])
    else:
        return [], []
    if not isinstance(children, list) or not conjunctive:
        return [], []
    holding: list[dict[str, Any]] = []
    failing: list[dict[str, Any]] = []
    for child in children:
        held, unheld = _guaranteed_leaves(child, negated)
        holding.extend(held)
        failing.extend(unheld)
    return holding, failing


def _flags_set_by(effects: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    raw = effects.get("set_flag")
    for entry in raw if isinstance(raw, list) else [raw]:
        if isinstance(entry, str) and entry.strip():
            names.add(entry.strip())
        elif isinstance(entry, dict) and entry.get("value", True) not in (False, None, 0, ""):
            name = str(entry.get("name", entry.get("flag", "")) or "").strip()
            if name:
                names.add(name)
    return names


def _check_effect_guards(
    condition: Any, effects: Any, where: str, path: Path, issues: list[ContentSetIssue]
) -> None:
    """Warn where a choice can be taken again, or can fail half-way.

    A dialogue choice can be chosen as often as the player likes and effects are not
    transactional, so two things the engine cannot make safe are the author's to
    guard, and the validator says so:

    - a `raise` is permanent, so it must not be repeatable: the choice's condition
      has to require a flag unset that the same choice then sets. And a large one
      is worth a second look even then.
    - a `take_gold` / `take_item` beside something given is a service: without a
      condition proving the character can pay, a character who cannot pay still
      receives the rest.
    """
    from engine.dialogue.effects import RAISE_LARGE

    if not isinstance(effects, dict):
        return
    holding, failing = _guaranteed_leaves(condition)
    label = f"{where}.effects"

    raised = effects.get("raise")
    if isinstance(raised, dict):
        unset = {str(leaf.get("flag", "")).strip() for leaf in failing if leaf.get("kind") == "flag"}
        if not (unset & _flags_set_by(effects)):
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{label} effect raise can be repeated: gate the choice with a 'not flag' condition on a "
                f"flag the same choice sets (a raise is treasure or a reward, not something to buy twice)",
            ))
        for key, limit in (("max_health", RAISE_LARGE["max_health"]), ("max_mana", RAISE_LARGE["max_mana"])):
            amount = raised.get(key)
            if isinstance(amount, int) and not isinstance(amount, bool) and amount > limit:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"{label} effect raise is large ({key} +{amount}; over {limit}): confirm that is intended",
                ))
        for stat, gain in (raised.get("stats") or {}).items() if isinstance(raised.get("stats"), dict) else ():
            if isinstance(gain, int) and not isinstance(gain, bool) and gain > RAISE_LARGE["stats"]:
                issues.append(ContentSetIssue(
                    "warning", str(path),
                    f"{label} effect raise is large ({stat} +{gain}; over {RAISE_LARGE['stats']}): confirm that is intended",
                ))

    benefits = [name for name in _BENEFIT_EFFECTS if name in effects]
    if not benefits:
        return
    price = effects.get("take_gold")
    if isinstance(price, int) and not isinstance(price, bool) and price > 0:
        covered = any(
            leaf.get("kind") == "gold_at_least" and isinstance(leaf.get("value"), (int, float))
            and leaf["value"] >= price
            for leaf in holding
        )
        if not covered:
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{label} effect take_gold has no gold_at_least guard of at least {price} on the choice, so a "
                f"character who cannot pay still receives the rest ({', '.join(benefits)}); effects are not transactional",
            ))
    from engine.dialogue.effects import entry_pairs

    for item_id, _quantity in entry_pairs(effects.get("take_item")):
        if not any(leaf.get("kind") == "has_item" and str(leaf.get("item_id", "")) == item_id for leaf in holding):
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{label} effect take_item '{item_id}' has no has_item guard on the choice, so a character who "
                f"does not carry it still receives the rest ({', '.join(benefits)}); effects are not transactional",
            ))


def _check_node_effects_do_not_raise(
    effects: Any, where: str, path: Path, issues: list[ContentSetIssue]
) -> None:
    """A node's own effects run every time the node is reached, and cannot be guarded."""
    if isinstance(effects, dict) and "raise" in effects:
        issues.append(ContentSetIssue(
            "warning", str(path),
            f"{where} effect raise in a node's own effects runs every time the node is reached and cannot be "
            f"guarded; put it on a choice that sets a flag and requires it unset",
        ))


def _effect_identifiers(value: Any) -> list[str]:
    """Ids named by one effect value, in any of the shapes the engine reads."""
    from engine.dialogue.effects import entry_pairs

    return [identifier for identifier, _quantity in entry_pairs(value)]


def _check_reveal_exit(
    reveal: dict[str, Any], where: str, content_root: Path, path: Path, issues: list[ContentSetIssue]
) -> None:
    """A `reveal_exit` must name a room that really has that hidden exit."""
    room_ref = str(reveal.get("room", "") or "").strip()
    direction = str(reveal.get("direction", "") or "").strip().lower()
    if not room_ref or not direction:
        return  # `effect_shape_issues` says which is missing
    region_id, _, room_id = room_ref.partition(":")
    if not room_id:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{where} effect reveal_exit.room must be 'region:room', got '{room_ref}'",
        ))
        return
    region_path = content_root / "regions" / f"{region_id}.json"
    if not region_path.is_file():
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} effect reveal_exit names missing region '{region_id}'"
        ))
        return
    payload = _load_json(region_path, issues, "region definitions")
    rooms = payload.get("rooms", {}) if isinstance(payload, dict) else {}
    room = rooms.get(room_id) if isinstance(rooms, dict) else None
    if not isinstance(room, dict):
        issues.append(ContentSetIssue(
            "error", str(path), f"{where} effect reveal_exit names missing room '{room_ref}'"
        ))
        return
    hidden = (room.get("properties") or {}).get("hidden_exits", {})
    if not isinstance(hidden, dict) or direction not in hidden:
        issues.append(ContentSetIssue(
            "error", str(path),
            f"{where} effect reveal_exit opens '{direction}' in '{room_ref}', "
            f"but that room declares no hidden exit there",
        ))


# What `World._evaluate_exit_gate` reads for each requirement type, and what
# `Room.apply_elemental_interaction` reads for each reaction. Published so the editor's
# panel and the vocabulary dump are checked against them (`schema_parity_smoke.gd`).
EXIT_REQUIREMENT_KEYS = {
    "skill": ("type", "skill_name", "difficulty", "failure_message"),
    "locked": ("type", "key_id", "pick_difficulty", "consume", "failure_message"),
    "condition": ("type", "condition", "consume", "failure_message"),
    "warning": ("type", "scene", "failure_message"),
    "vehicle": ("type", "vehicle", "failure_message"),
}
ENV_INTERACTION_KEYS = {
    "clear_exit_req": ("type", "direction", "duration", "permanent", "message"),
    "suppress_hazard": ("type", "duration", "permanent", "message", "channel"),
}


def _check_exit_consume_list(
    consume: Any, ids: dict[str, set[str]], condition: Any, label: str, where: str, path: Path,
    issues: list[ContentSetIssue],
) -> None:
    """A `condition` requirement's `consume`: items spent when the player goes through."""
    from engine.dialogue.effects import effect_shape_issues, entry_pairs

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(path), f"{where} {label}.consume {message}"))

    if not isinstance(consume, list) or not consume:
        error("must be a non-empty list of items (ids, or {item_id, quantity})")
        return
    problems = effect_shape_issues({"take_item": consume})
    for problem in problems:
        error(problem.replace("take_item", "entry", 1))
    if problems:
        return
    holding, _failing = _guaranteed_leaves(condition)
    required = {str(leaf.get("item_id", "")) for leaf in holding if leaf.get("kind") == "has_item"}
    for item_id, _quantity in entry_pairs(consume):
        if ids["items"] and item_id not in ids["items"]:
            error(f"names item '{item_id}', which is not defined in this content set")
        elif item_id not in required:
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{where} {label}.consume spends '{item_id}', but the condition does not require holding it, "
                f"so the way can open without it having anything to spend",
            ))


def _validate_room_passage_properties(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Room `properties.exit_requirements` and `properties.env_interactions`.

    Both fail open. `World.move_player` checks a requirement only when its type
    is `skill` or `locked` and only for a direction the room actually has, so a
    misspelt type or direction leaves the way free; a `skill` requirement whose
    name is misspelt as `skill` rolls against no skill at all. An interaction
    (`Room.apply_elemental_interaction`, fired by a spell's damage type) that
    clears a requirement the room does not have, or suppresses a hazard the room
    does not carry, does nothing.
    """
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    damage_types: set[str] = set()
    elements = _load_json(content_root / "combat" / "elements.json", [], "combat vocabulary") if (content_root / "combat" / "elements.json").is_file() else None
    if isinstance(elements, dict) and isinstance(elements.get("valid_damage_types"), list):
        damage_types = {str(value) for value in elements["valid_damage_types"]}
    hazard_channels: dict[str, str] = {}
    if isinstance(elements, dict) and isinstance(elements.get("hazards"), dict):
        for hazard_id, record in elements["hazards"].items():
            if isinstance(record, dict) and isinstance(record.get("channel"), str):
                hazard_channels[str(hazard_id)] = record["channel"].strip()

    def whole(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    condition_ids: dict[str, set[str]] | None = None   # built on the first condition requirement

    def condition_ids_for() -> dict[str, set[str]]:
        nonlocal condition_ids
        if condition_ids is None:
            condition_ids = _content_identifier_sets(content_root, [])
        return condition_ids

    for path in sorted(region_dir.glob("*.json")):
        region = _load_json(path, [], "region definitions")
        if not isinstance(region, dict) or isinstance(region.get("themes"), dict):
            continue
        region_id = str(region.get("region_id", path.stem))
        rooms = region.get("rooms", {})
        if not isinstance(rooms, dict):
            continue
        for room_id, room in rooms.items():
            if not isinstance(room, dict) or not isinstance(room.get("properties"), dict):
                continue
            properties = room["properties"]
            where = f"room '{region_id}:{room_id}'"
            source = str(path)

            def error(message: str) -> None:
                issues.append(ContentSetIssue("error", source, f"{where} {message}"))

            directions = set(room.get("exits", {}) or {}) if isinstance(room.get("exits"), dict) else set()
            hidden = properties.get("hidden_exits", {})
            if isinstance(hidden, dict):
                directions |= set(hidden)

            def warn(message: str) -> None:
                issues.append(ContentSetIssue("warning", source, f"{where} {message}"))

            requirements = properties.get("exit_requirements")
            requirement_directions: set[str] = set()
            if requirements is not None:
                if not isinstance(requirements, dict):
                    error("properties.exit_requirements must be an object of direction -> requirement")
                    requirements = {}
                for direction, requirement in requirements.items():
                    label = f"properties.exit_requirements.{direction}"
                    requirement_directions.add(direction)
                    if direction not in directions:
                        error(f"{label} guards a direction the room has no exit for, so it never applies")
                    if not isinstance(requirement, dict):
                        error(f"{label} must be an object")
                        continue
                    kind = requirement.get("type")
                    if kind not in EXIT_REQUIREMENT_KEYS:
                        error(f"{label}.type must be 'skill', 'locked', 'condition', 'warning' or 'vehicle' (anything else leaves the way open)")
                        continue
                    for key in requirement:
                        if key not in EXIT_REQUIREMENT_KEYS[kind]:
                            error(f"{label}.{key} is not read for a '{kind}' requirement (known: {', '.join(EXIT_REQUIREMENT_KEYS[kind])})")
                    if "failure_message" in requirement and not isinstance(requirement["failure_message"], str):
                        error(f"{label}.failure_message must be a string")
                    if kind == "skill":
                        if not isinstance(requirement.get("skill_name"), str) or not requirement["skill_name"].strip():
                            error(f"{label}.skill_name is required for a skill requirement")
                        if "difficulty" in requirement and not whole(requirement["difficulty"]):
                            error(f"{label}.difficulty must be a non-negative integer")
                    elif kind == "condition":
                        if "consume" in requirement:
                            _check_exit_consume_list(requirement["consume"], condition_ids_for(), requirement.get("condition"), label, where, path, issues)
                        condition = requirement.get("condition")
                        if not isinstance(condition, (dict, list)) or not condition:
                            error(f"{label}.condition is required, and may not be empty (an empty condition is open to everyone)")
                        else:
                            _check_condition(condition, f"{where} {label}.condition", path, condition_ids_for(), issues)
                    elif kind == "vehicle":
                        wanted = requirement.get("vehicle")
                        listed = [wanted] if isinstance(wanted, str) else wanted
                        if not isinstance(listed, list) or not listed or not all(isinstance(v, str) and v.strip() for v in listed):
                            error(f"{label}.vehicle is required: a vehicle id, or a list of them")
                        else:
                            vehicle_ids = condition_ids_for()["vehicles"]
                            for vehicle_id in listed:
                                if vehicle_id not in vehicle_ids:
                                    error(f"{label}.vehicle names vehicle '{vehicle_id}', which is not in data/vehicles of this content set")
                    elif kind == "warning":
                        scene = requirement.get("scene")
                        message = requirement.get("failure_message")
                        if scene is None and not (isinstance(message, str) and message.strip()):
                            error(f"{label} needs a scene or a failure_message: it is the warning the first attempt is met with")
                        if scene is not None:
                            scene_ids = condition_ids_for()["scenes"]
                            if not isinstance(scene, str) or not scene.strip():
                                error(f"{label}.scene must be a scene id")
                            elif scene_ids and scene not in scene_ids:
                                error(f"{label}.scene names scene '{scene}', which is not in data/scenes of this content set")
                    else:
                        key_id = requirement.get("key_id")
                        if key_id is not None and key_id not in item_ids:
                            error(f"{label}.key_id references missing item '{key_id}'")
                        if "consume" in requirement:
                            if not isinstance(requirement["consume"], bool):
                                error(f"{label}.consume must be true or false (a key is spent whole)")
                            elif requirement["consume"] and not key_id:
                                error(f"{label}.consume spends the key, but the requirement names no key_id")
                        if "pick_difficulty" in requirement and not whole(requirement["pick_difficulty"]):
                            error(f"{label}.pick_difficulty must be a non-negative integer (over 100 means it cannot be picked)")

            interactions = properties.get("env_interactions")
            if interactions is None:
                continue
            if not isinstance(interactions, dict):
                error("properties.env_interactions must be an object of damage type -> reaction")
                continue
            for damage_type, reaction in interactions.items():
                label = f"properties.env_interactions.{damage_type}"
                if damage_types and damage_type not in damage_types:
                    error(f"{label} names a damage type combat/elements.json does not declare, so no spell triggers it")
                if not isinstance(reaction, dict):
                    error(f"{label} must be an object")
                    continue
                kind = reaction.get("type")
                if kind not in ENV_INTERACTION_KEYS:
                    error(f"{label}.type must be 'clear_exit_req' or 'suppress_hazard'")
                    continue
                for key in reaction:
                    if key not in ENV_INTERACTION_KEYS[kind]:
                        error(f"{label}.{key} is not read for '{kind}' (known: {', '.join(ENV_INTERACTION_KEYS[kind])})")
                if "permanent" in reaction and not isinstance(reaction["permanent"], bool):
                    error(f"{label}.permanent must be true or false")
                elif reaction.get("permanent") is True and "duration" in reaction:
                    error(f"{label} is permanent, so a duration contradicts it (there is nothing to revert after)")
                duration = reaction.get("duration", 10.0)
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                    error(f"{label}.duration must be a positive number of seconds")
                if "message" in reaction and not isinstance(reaction["message"], str):
                    error(f"{label}.message must be a string")
                if kind == "clear_exit_req" and reaction.get("direction") not in requirement_directions:
                    error(f"{label}.direction must name one of this room's exit_requirements, or the reaction does nothing")
                elif kind == "clear_exit_req" and isinstance(requirements, dict) \
                        and isinstance(requirements.get(reaction.get("direction")), dict) \
                        and requirements[reaction["direction"]].get("type") == "condition":
                    warn(f"{label} is a clear_exit_req that clears a 'condition' requirement, so this element opens a way the condition was meant to keep shut")
                if kind == "suppress_hazard":
                    from engine.world.environment import hazard_entries
                    room_hazards = [str(entry.get("type", "")).strip() for entry in hazard_entries(properties)]
                    if not room_hazards:
                        error(f"{label} suppresses a hazard, but the room has no hazard_type or hazards")
                        continue
                    # A `channel` narrows the reaction to the hazards dealing
                    # through it; one that matches none of the room's does nothing.
                    wanted = reaction.get("channel")
                    if wanted is None:
                        continue
                    channels = [wanted] if isinstance(wanted, str) else wanted
                    if not isinstance(channels, list) or not channels or any(not isinstance(value, str) or not value.strip() for value in channels):
                        error(f"{label}.channel must be a damage channel or a list of them")
                        continue
                    for value in channels:
                        if damage_types and value not in damage_types:
                            error(f"{label}.channel '{value}' is not one of this set's damage types")
                    if not any(hazard_channels.get(hazard_id) in channels for hazard_id in room_hazards):
                        error(f"{label}.channel matches none of this room's hazards ({', '.join(room_hazards)}), so the reaction does nothing")


_CAMPAIGN_KEYS = ("campaign_id", "name", "description", "start_node_id", "nodes")
_CAMPAIGN_NODE_KEYS = ("description", "quest_template_id", "type", "transitions", "outcome", "effects")
_CAMPAIGN_TRANSITION_KEYS = ("trigger", "target_node_id", "narrative_text", "pace", "chance")
