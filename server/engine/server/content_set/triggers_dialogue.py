"""Triggers, scenes and dialogue graphs.

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
from .effects_conditions import (_check_condition, _check_effect_block, _check_effect_guards, _check_node_effects_do_not_raise, _check_room_reference)
from .identifiers import (_content_identifier_sets, _with_ruleset_stats)


def _validate_triggers(
    content_root: Path, issues: list[ContentSetIssue], ruleset_payload: Any = None
) -> None:
    """`data/triggers/*.json`: objects of triggers keyed by id (`engine/world/triggers.py`).

    Effects and conditions are checked exactly as a conversation's are, plus what only a
    trigger has: a known event, the room it fires in, a `once` the runner understands,
    and an id used once across the set. A repeating trigger (`once: false`) is held to the
    same repeat guard a dialogue choice is.
    """
    from engine.world.triggers import EVENT_FIELDS, EVENT_REQUIRED, ONCE_MODES, TRIGGER_EVENTS, TRIGGER_KEYS

    directory = content_root / "triggers"
    if not directory.is_dir():
        return
    ids = _with_ruleset_stats(_content_identifier_sets(content_root, []), ruleset_payload)
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, "triggers")
        if payload is None:
            continue
        if not isinstance(payload, dict):
            issues.append(ContentSetIssue("error", str(path), "a triggers file must be an object of triggers keyed by id"))
            continue
        for trigger_id, definition in payload.items():
            if str(trigger_id).startswith("_"):
                continue
            label = f"trigger '{trigger_id}'"
            if trigger_id in seen:
                issues.append(ContentSetIssue(
                    "error", str(path), f"{label} is defined twice (also in {seen[trigger_id]}); an id names one trigger"
                ))
                continue
            seen[trigger_id] = path.name
            if not isinstance(definition, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label} must be an object"))
                continue
            for key in definition:
                if key not in TRIGGER_KEYS:
                    issues.append(ContentSetIssue(
                        "error", str(path), f"{label} has unknown key '{key}' (known: {', '.join(TRIGGER_KEYS)})"
                    ))
            on = definition.get("on")
            if not isinstance(on, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label}.on must be an object with an event, a region and a room"))
            else:
                event = on.get("event")

                def has(key: str) -> bool:
                    return isinstance(on.get(key), str) and bool(on[key].strip())

                if event not in TRIGGER_EVENTS:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{label}.on.event {event!r} is not an event this engine fires (known: {', '.join(TRIGGER_EVENTS)})",
                    ))
                else:
                    for key in on:
                        if key != "event" and key not in EVENT_FIELDS[event]:
                            issues.append(ContentSetIssue(
                                "error", str(path),
                                f"{label}.on.{key} is not read by a {event} trigger (it reads: {', '.join(EVENT_FIELDS[event])})",
                            ))
                    for key in EVENT_REQUIRED[event]:
                        if not has(key):
                            issues.append(ContentSetIssue("error", str(path), f"{label}.on needs a {key} for a {event} trigger"))
                    if has("region") != has("room") and "region" in EVENT_FIELDS[event]:
                        issues.append(ContentSetIssue("error", str(path), f"{label}.on needs region and room together, or neither"))
                    if has("region") and has("room"):
                        _check_room_reference(on["region"], on["room"], f"{label}.on", path, ids, issues)
                    if event == "npc_killed" and has("npc"):
                        known = ids["npcs"] | ids["npc_instances"]
                        if known and on["npc"] not in known:
                            issues.append(ContentSetIssue(
                                "error", str(path),
                                f"{label}.on.npc '{on['npc']}' is neither an NPC template nor a placed NPC in this content set",
                            ))
            if "when" in definition:
                _check_condition(definition["when"], f"{label}.when", path, ids, issues)
            once = definition.get("once", "player")
            if once is not False and once not in ONCE_MODES:
                issues.append(ContentSetIssue(
                    "error", str(path), f"{label}.once must be 'player', 'world' or false (every time); got {once!r}"
                ))
            effects = definition.get("effects")
            if not isinstance(effects, dict) or not effects:
                issues.append(ContentSetIssue("error", str(path), f"{label}.effects must be a non-empty object of effects"))
                continue
            _check_effect_block(effects, f"{label}.effects", path, ids, content_root, issues)
            if once is False:
                _check_effect_guards(definition.get("when"), effects, label, path, issues)


def _validate_scenes(
    content_root: Path, issues: list[ContentSetIssue], ruleset_payload: Any = None
) -> None:
    """`data/scenes/*.json`: objects of scenes keyed by id (`engine/world/scenes.py`).

    A scene is a list of beats, each `{text, after, pace, effects}`; its effects are checked exactly as a trigger's
    or a conversation's are, so a beat cannot spawn a creature nobody authored or send the player to a room that is
    not there. An id names one scene across the set, and a scene needs something to tell or do.
    """
    from engine.utils import pacing
    from engine.world.scenes import BEAT_KEYS, MAX_WAIT, SCENE_KEYS

    directory = content_root / "scenes"
    if not directory.is_dir():
        return
    ids = _with_ruleset_stats(_content_identifier_sets(content_root, []), ruleset_payload)
    seen: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        payload = _load_json(path, issues, "scenes")
        if payload is None:
            continue
        if not isinstance(payload, dict):
            issues.append(ContentSetIssue("error", str(path), "a scenes file must be an object of scenes keyed by id"))
            continue
        for scene_id, definition in payload.items():
            if str(scene_id).startswith("_"):
                continue
            label = f"scene '{scene_id}'"
            if scene_id in seen:
                issues.append(ContentSetIssue(
                    "error", str(path), f"{label} is defined twice (also in {seen[scene_id]}); an id names one scene"
                ))
                continue
            seen[scene_id] = path.name
            if not isinstance(definition, dict):
                issues.append(ContentSetIssue("error", str(path), f"{label} must be an object"))
                continue
            for key in definition:
                if key not in SCENE_KEYS:
                    issues.append(ContentSetIssue(
                        "error", str(path), f"{label} has unknown key '{key}' (known: {', '.join(SCENE_KEYS)})"
                    ))
            if "lock" in definition and not isinstance(definition["lock"], bool):
                issues.append(ContentSetIssue("error", str(path), f"{label}.lock must be true or false (false leaves the player free to act)"))
            if "note" in definition and not isinstance(definition["note"], str):
                issues.append(ContentSetIssue("error", str(path), f"{label}.note must be text"))
            beats = definition.get("beats")
            if not isinstance(beats, list) or not beats:
                issues.append(ContentSetIssue("error", str(path), f"{label}.beats must be a non-empty list of beats"))
                continue
            for index, beat in enumerate(beats):
                where = f"{label}.beats[{index}]"
                if not isinstance(beat, dict):
                    issues.append(ContentSetIssue("error", str(path), f"{where} must be an object ({{text, after, pace, effects}})"))
                    continue
                for key in beat:
                    if key not in BEAT_KEYS:
                        issues.append(ContentSetIssue("error", str(path), f"{where} has unknown key '{key}' (known: {', '.join(BEAT_KEYS)})"))
                text = beat.get("text")
                if "text" in beat and (not isinstance(text, str) or not text.strip()):
                    issues.append(ContentSetIssue("error", str(path), f"{where}.text must be the words to tell"))
                if "text" not in beat and not beat.get("effects"):
                    issues.append(ContentSetIssue("error", str(path), f"{where} tells nothing and does nothing: give it a text or effects"))
                if "after" in beat:
                    after = beat["after"]
                    if isinstance(after, bool) or not isinstance(after, (int, float)) or not 0 <= after <= MAX_WAIT:
                        issues.append(ContentSetIssue(
                            "error", str(path), f"{where}.after must be a number of seconds from 0 to {MAX_WAIT} (the wait after the beat before)"
                        ))
                if beat.get("pace") not in (None, "instant") and pacing.resolve_pace(beat.get("pace")) is None:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{where}.pace '{beat.get('pace')}' is not a pace (a name -- {', '.join(pacing.TEXT_PACES)} -- "
                        f"or characters per second from {pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})",
                    ))
                if "effects" in beat:
                    if not isinstance(beat["effects"], dict) or not beat["effects"]:
                        issues.append(ContentSetIssue("error", str(path), f"{where}.effects must be a non-empty object of effects"))
                    else:
                        _check_effect_block(beat["effects"], f"{where}.effects", path, ids, content_root, issues)


def _validate_dialogue_content(
    content_root: Path, issues: list[ContentSetIssue], ruleset_payload: Any = None
) -> None:
    """Validate authored conversations, their references, and their wiring.

    The point is the P5 definition of done: a missing graph, a `next_node` that
    does not exist, a condition kind the engine cannot evaluate, or an effect
    naming an item nobody authored must fail *validation*, never a conversation.
    A player should not be the one who discovers that a choice leads nowhere.
    """
    from engine.dialogue.manager import parse_graph
    from engine.utils import pacing

    dialogue_dir = content_root / "dialogue"
    graphs: dict[str, Any] = {}
    graph_paths: dict[str, Path] = {}

    if dialogue_dir.is_dir():
        for path in sorted(dialogue_dir.glob("*.json")):
            payload = _load_json(path, issues, "dialogue graphs")
            if payload is None:
                continue
            graph_id = str(payload.get("id") or path.stem) if isinstance(payload, dict) else path.stem
            graph, graph_issues = parse_graph(payload, graph_id, path.name)
            for issue in graph_issues:
                issues.append(ContentSetIssue("error", str(path), issue))
            if graph is None:
                continue
            if graph_id in graphs:
                issues.append(ContentSetIssue(
                    "error", str(path), f"duplicate dialogue graph id '{graph_id}'"
                ))
                continue
            graphs[graph_id] = graph
            graph_paths[graph_id] = path

    ids = _with_ruleset_stats(_content_identifier_sets(content_root, issues), ruleset_payload)

    # A graph nobody points at is dead content; a pointer to no graph is a
    # broken conversation. The second is an error, the first a warning.
    referenced: set[str] = set()
    for path in sorted((content_root / "npcs").glob("*.json")):
        payload = _load_json(path, issues, "NPC definitions")
        if not isinstance(payload, dict):
            continue
        for template_id, template in payload.items():
            if str(template_id).startswith("_") or not isinstance(template, dict):
                continue
            properties = template.get("properties")
            if not isinstance(properties, dict):
                continue
            graph_id = str(properties.get("dialogue", "") or "").strip()
            if not graph_id:
                continue
            referenced.add(graph_id)
            if graph_id not in graphs:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"NPC '{template_id}' references missing dialogue graph '{graph_id}'",
                ))

    for graph_id, graph in graphs.items():
        path = graph_paths[graph_id]
        label = f"dialogue graph '{graph_id}'"
        if graph_id not in referenced:
            issues.append(ContentSetIssue(
                "warning", str(path),
                f"{label} is not referenced by any NPC template",
            ))
        for position, entry in enumerate(graph.entries):
            _check_condition(entry.get("condition"), f"{label} entries[{position}].condition", path, ids, issues)
        for node in graph.nodes.values():
            where = f"{label} node '{node.node_id}'"

            _check_effect_block(node.effects, f"{where}.effects", path, ids, content_root, issues)
            _check_node_effects_do_not_raise(node.effects, where, path, issues)
            if "narration" in node.raw and not isinstance(node.raw["narration"], bool):
                issues.append(ContentSetIssue("error", str(path), f"{where}.narration must be true or false"))
            if "must_answer" in node.raw:
                if not isinstance(node.raw["must_answer"], bool):
                    issues.append(ContentSetIssue("error", str(path), f"{where}.must_answer must be true or false"))
                elif node.raw["must_answer"] and (node.ends_conversation or not node.choices):
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"{where} is a must_answer scene with nothing to answer, so the player could never get out of it",
                    ))
            if node.pace not in (None, "instant") and pacing.resolve_pace(node.pace) is None:
                issues.append(ContentSetIssue(
                    "error", str(path),
                    f"{where}.pace {node.pace!r} is not a pace, so the text is shown at once "
                    f"(a name -- {', '.join(pacing.TEXT_PACES)} -- or characters per second from "
                    f"{pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})",
                ))
            for choice in node.choices:
                choice_where = f"{where}.choices[{choice.index}]"
                _check_condition(choice.condition, f"{choice_where}.condition", path, ids, issues)
                _check_effect_block(choice.effects, f"{choice_where}.effects", path, ids, content_root, issues)
                _check_effect_guards(choice.condition, choice.effects, choice_where, path, issues)
                if choice.check:
                    _check_effect_block(
                        choice.check.get("success_effects"), f"{choice_where}.check.success_effects",
                        path, ids, content_root, issues,
                    )
                    _check_effect_block(
                        choice.check.get("fail_effects"), f"{choice_where}.check.fail_effects",
                        path, ids, content_root, issues,
                    )
