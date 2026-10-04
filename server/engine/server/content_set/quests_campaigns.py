"""Campaigns, quest rewards, stages, instance quests, field interactions and choice outcomes.

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
from .effects_conditions import (_CAMPAIGN_KEYS, _CAMPAIGN_NODE_KEYS, _CAMPAIGN_TRANSITION_KEYS, _check_effect_block)
from .identifiers import (_content_identifier_sets, _with_ruleset_stats)
from .knowledge import (_knowledge_region_ids)


def _validate_campaigns(content_root: Path, issues: list[ContentSetIssue], ruleset_payload: Any = None) -> None:
    """`campaigns/*.json` (`campaign/campaign_models.py`, `campaign_manager.py`).

    A campaign missing a required key fails to load with a log line. Past that
    every mistake is a campaign that silently stops: a node type the manager
    does not act on, a QUEST node with no quest or no way out, a transition
    that names no node, uses a trigger no quest reports, or sits behind an
    earlier `SUCCESS` that already matches it. A transition's `conditions` are
    never read. A CUTSCENE node applies its `effects` and moves on; a DIALOGUE node
    applies them and waits for an `advance_campaign` effect somewhere in the set.
    """
    from engine.campaign.campaign_models import CAMPAIGN_NODE_TYPES, CAMPAIGN_TRIGGERS

    campaign_dir = content_root / "campaigns"
    if not campaign_dir.is_dir():
        return
    quest_ids = _load_definition_ids(content_root / "quests", "quest definitions", issues)
    effect_ids = _with_ruleset_stats(_content_identifier_sets(content_root, []), ruleset_payload)
    advancing_text = None
    seen: dict[str, str] = {}
    for path in sorted(campaign_dir.glob("*.json")):
        payload = _load_json(path, issues, "campaign")
        if payload is None:
            continue
        source = str(path)

        def error(message: str) -> None:
            issues.append(ContentSetIssue("error", source, message))

        if not isinstance(payload, dict):
            error("a campaign file must be an object")
            continue
        for key in payload:
            if not str(key).startswith("_") and key not in _CAMPAIGN_KEYS:
                error(f"'{key}' is not read (known: {', '.join(_CAMPAIGN_KEYS)})")
        for key in ("campaign_id", "name", "description", "start_node_id"):
            if not isinstance(payload.get(key), str) or (key != "description" and not payload[key].strip()):
                error(f"{key} is required (without it the campaign does not load)")
        campaign_id = payload.get("campaign_id")
        if isinstance(campaign_id, str) and campaign_id.strip():
            if campaign_id in seen:
                error(f"campaign_id '{campaign_id}' is also declared by {seen[campaign_id]}; only one of them loads")
            seen[campaign_id] = path.name
        nodes = payload.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            error("nodes must be a non-empty object of node id -> node")
            continue
        start = payload.get("start_node_id")
        if isinstance(start, str) and start and start not in nodes:
            error(f"start_node_id '{start}' is not one of this campaign's nodes, so the campaign cannot start")

        for node_id, node in nodes.items():
            label = f"nodes.{node_id}"
            if not isinstance(node, dict):
                error(f"{label} must be an object")
                continue
            for key in node:
                if not str(key).startswith("_") and key not in _CAMPAIGN_NODE_KEYS:
                    error(f"{label}.{key} is not read (known: {', '.join(_CAMPAIGN_NODE_KEYS)})")
            node_type = node.get("type", "QUEST")
            transitions = node.get("transitions", [])
            if node_type not in CAMPAIGN_NODE_TYPES:
                error(f"{label}.type '{node_type}' is not acted on (only {', '.join(CAMPAIGN_NODE_TYPES)}); the campaign stops there for good")
            elif node_type in ("CUTSCENE", "DIALOGUE"):
                if not transitions:
                    error(f"{label} is a {node_type} node with no transitions: it leads nowhere and the campaign never ends")
                if "effects" in node and not isinstance(node["effects"], dict):
                    error(f"{label}.effects must be an object of effects")
                else:
                    _check_effect_block(node.get("effects"), f"{label}.effects", path, effect_ids, content_root, issues)
                    if node_type == "CUTSCENE" and isinstance(node.get("effects"), dict) and "advance_campaign" in node["effects"]:
                        error(f"{label}.effects advance_campaign is for a DIALOGUE node; a CUTSCENE node moves on by itself")
                if node_type == "DIALOGUE" and isinstance(campaign_id, str):
                    if advancing_text is None:
                        advancing_text = _text_of_set_files(content_root, exclude=campaign_dir)
                    if not any('"advance_campaign"' in text and campaign_id in text for text in advancing_text):
                        issues.append(ContentSetIssue(
                            "warning", source,
                            f"{label} is a DIALOGUE node but nothing in this set carries an advance_campaign effect naming '{campaign_id}', so it waits forever",
                        ))
            elif node_type == "QUEST":
                quest = node.get("quest_template_id")
                if not isinstance(quest, str) or not quest.strip():
                    error(f"{label} is a QUEST node with no quest_template_id, so nothing starts and the campaign stops")
                elif quest not in quest_ids:
                    error(f"{label}.quest_template_id references missing quest '{quest}'")
                if not transitions:
                    error(f"{label} is a QUEST node with no transitions: finishing its quest leads nowhere and the campaign never ends")
            else:
                if not isinstance(node.get("outcome"), str) or not node["outcome"].strip():
                    error(f"{label} is an END node and needs an outcome (knowledge topics and the summary read it)")
                if transitions:
                    error(f"{label} is an END node; its transitions are never followed")
            if node_type in ("QUEST", "END") and node.get("effects"):
                error(f"{label}.effects is never applied (only CUTSCENE and DIALOGUE nodes apply effects)")
            if not isinstance(transitions, list):
                error(f"{label}.transitions must be an array")
                continue
            success_seen = False
            for index, transition in enumerate(transitions):
                t_label = f"{label}.transitions[{index}]"
                if not isinstance(transition, dict):
                    error(f"{t_label} must be an object")
                    continue
                for key in transition:
                    if key == "conditions":
                        if transition[key]:
                            error(f"{t_label}.conditions are never read; the transition fires regardless")
                    elif not str(key).startswith("_") and key not in _CAMPAIGN_TRANSITION_KEYS:
                        error(f"{t_label}.{key} is not read (known: {', '.join(_CAMPAIGN_TRANSITION_KEYS)})")
                trigger = transition.get("trigger", "SUCCESS")
                if trigger not in CAMPAIGN_TRIGGERS:
                    error(f"{t_label}.trigger '{trigger}' is never reported by a quest (known: {', '.join(CAMPAIGN_TRIGGERS)}), so it never fires")
                elif success_seen:
                    error(f"{t_label} can never fire: an earlier SUCCESS transition that always fires already matches every success")
                chance = transition.get("chance", 1.0)
                if isinstance(chance, bool) or not isinstance(chance, (int, float)) or not 0 < chance <= 1:
                    error(f"{t_label}.chance must be a number above 0 and at most 1")
                elif trigger == "SUCCESS" and chance >= 1:
                    success_seen = True
                if transition.get("target_node_id") not in nodes:
                    error(f"{t_label}.target_node_id '{transition.get('target_node_id')}' is not one of this campaign's nodes")
                if "narrative_text" in transition and not isinstance(transition["narrative_text"], str):
                    error(f"{t_label}.narrative_text must be a string")
                from engine.utils import pacing
                if transition.get("pace") not in (None, "instant") and pacing.resolve_pace(transition.get("pace")) is None:
                    error(f"{t_label}.pace '{transition.get('pace')}' is not a pace (a name -- {', '.join(pacing.TEXT_PACES)} -- or characters per second from {pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})")

        if isinstance(start, str) and start in nodes:
            reachable = {start}
            frontier = [start]
            while frontier:
                current = nodes.get(frontier.pop(), {})
                for transition in current.get("transitions", []) if isinstance(current, dict) else []:
                    target = transition.get("target_node_id") if isinstance(transition, dict) else None
                    if target in nodes and target not in reachable:
                        reachable.add(target)
                        frontier.append(target)
            for node_id in nodes:
                if node_id not in reachable:
                    issues.append(ContentSetIssue("warning", source, f"nodes.{node_id} cannot be reached from start_node_id '{start}'"))
            if not any(isinstance(nodes[n], dict) and nodes[n].get("type") == "END" for n in reachable):
                error(f"no END node can be reached from start_node_id '{start}', so the campaign never completes")
            # Cutscenes hand straight on, so a loop made only of them never lets the player act.
            def cutscene_next(node_id: str) -> list:
                node = nodes.get(node_id)
                if not isinstance(node, dict) or node.get("type") != "CUTSCENE":
                    return []
                return [t.get("target_node_id") for t in node.get("transitions", []) if isinstance(t, dict)]

            for node_id in nodes:
                stack, visited = list(cutscene_next(node_id)), set()
                while stack:
                    current = stack.pop()
                    if current == node_id:
                        error(f"nodes.{node_id} is part of a loop of CUTSCENE nodes with no quest or conversation in it; the campaign would never wait for the player")
                        break
                    if current in visited:
                        continue
                    visited.add(current)
                    stack.extend(cutscene_next(current))


def _text_of_set_files(content_root: Path, exclude: Path) -> list[str]:
    """The raw text of every JSON file under the set's data folders, for a plain search."""
    texts: list[str] = []
    for path in content_root.rglob("*.json"):
        if exclude in path.parents or "saves" in path.parts or "editor" in path.parts:
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return texts


QUEST_REWARD_KEYS = ("xp", "gold", "items", "generated_item_data", "relationships")


def _validate_quest_rewards(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`quests.json` rewards, as `QuestManager._grant_rewards` pays them.

    It compares `xp` and `gold` with `> 0` (a string raises), indexes each item
    reward's `item_id` and `quantity` directly (a missing quantity raises, and
    the quest completes without paying), and skips a relationship reward whose
    NPC is not in the world. Only instance quests had their rewards checked.
    """
    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, [], "quest definitions")
    if not isinstance(payload, dict):
        return
    item_ids = _load_definition_ids(content_root / "items", "item definitions", [])
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", [])

    def integer(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict) or "rewards" not in quest:
            continue
        label = f"quest '{quest_id}' rewards"

        def error(message: str) -> None:
            issues.append(ContentSetIssue("error", str(quests_path), f"{label}{message}"))

        rewards = quest["rewards"]
        if not isinstance(rewards, dict):
            error(" must be an object")
            continue
        for key in rewards:
            if not str(key).startswith("_") and key not in QUEST_REWARD_KEYS:
                error(f".{key} is not paid (known: {', '.join(QUEST_REWARD_KEYS)})")
        for key in ("xp", "gold"):
            if key in rewards and (not integer(rewards[key]) or rewards[key] < 0):
                error(f".{key} must be a whole number, 0 or more")
        items = rewards.get("items", [])
        if not isinstance(items, list):
            error(".items must be an array")
            items = []
        for index, entry in enumerate(items):
            where = f".items[{index}]"
            if not isinstance(entry, dict):
                error(f"{where} must be an object")
                continue
            if entry.get("item_id") not in item_ids:
                error(f"{where}.item_id references missing item {entry.get('item_id')!r}")
            if not integer(entry.get("quantity")) or entry["quantity"] < 1:
                error(f"{where}.quantity must be a whole number of at least 1 (it is read directly; without it the quest pays nothing)")
        if "generated_item_data" in rewards and not isinstance(rewards["generated_item_data"], dict):
            error(".generated_item_data must be an object")
        relationships = rewards.get("relationships", [])
        if not isinstance(relationships, list):
            error(".relationships must be an array")
            relationships = []
        for index, entry in enumerate(relationships):
            where = f".relationships[{index}]"
            if not isinstance(entry, dict):
                error(f"{where} must be an object")
                continue
            if entry.get("npc_template_id") not in npc_ids:
                error(f"{where}.npc_template_id references missing NPC template {entry.get('npc_template_id')!r}")
            if not integer(entry.get("amount")) or entry["amount"] == 0:
                error(f"{where}.amount must be a non-zero whole number")


# What a quest stage may say (`core/quests/*`). Keys beginning with "_" are the engine's own progress marks.
_STAGE_KEYS = (
    "stage_index", "description", "objective", "objectives_any", "turn_in_id", "turn_in_config",
    "completion_dialogue", "completion_narration", "ready_text", "start_dialogue",
    "spawn_on_entry", "spawn_on_start",
)
_STAGE_TEXT_KEYS = ("completion_dialogue", "completion_narration", "ready_text", "start_dialogue")
_INTRO_BEAT_KEYS = ("text", "after", "pace")


def _validate_stage_fields(content_root: Path, quests_path: Path, quest_id: str, index: int, stage: dict,
                           issues: list[ContentSetIssue], npc_ids: set, room_refs: set) -> None:
    """The text fields, the creature a stage brings in, and the told moments before it arrives."""
    from engine.utils import pacing
    import difflib

    label = f"quest '{quest_id}' stage {index}"

    def error(message: str) -> None:
        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.{message}"))

    for key in stage:
        if str(key).startswith("_") or key in _STAGE_KEYS:
            continue
        near = difflib.get_close_matches(str(key), _STAGE_KEYS, n=1, cutoff=0.7)
        issues.append(ContentSetIssue(
            "warning", str(quests_path),
            f"{label}.{key} is not a stage field the engine reads"
            + (f" (did you mean '{near[0]}'?)" if near else "")
            + f" (known: {', '.join(_STAGE_KEYS)})",
        ))
    for key in _STAGE_TEXT_KEYS:
        if key in stage and not isinstance(stage[key], str):
            error(f"{key} must be text")

    spawn = stage.get("spawn_on_start")
    if spawn is None:
        return
    if not isinstance(spawn, dict):
        error("spawn_on_start must be an object ({template_id, region_id, room_id})")
        return
    for key in ("template_id", "region_id", "room_id"):
        if not isinstance(spawn.get(key), str) or not spawn.get(key, "").strip():
            error(f"spawn_on_start.{key} must name what to bring in and where")
    if isinstance(spawn.get("template_id"), str) and npc_ids and spawn["template_id"] not in npc_ids:
        error(f"spawn_on_start.template_id '{spawn['template_id']}' is not an NPC this set defines")
    if (isinstance(spawn.get("region_id"), str) and isinstance(spawn.get("room_id"), str)
            and room_refs and f"{spawn['region_id']}:{spawn['room_id']}" not in room_refs):
        error(f"spawn_on_start names '{spawn['region_id']}:{spawn['room_id']}', which is not a room this set defines")
    if "name_override" in spawn and not isinstance(spawn["name_override"], str):
        error("spawn_on_start.name_override must be text")
    for key in spawn:
        if key not in ("template_id", "region_id", "room_id", "name_override", "intro"):
            error(f"spawn_on_start.{key} is not read (known: template_id, region_id, room_id, name_override, intro)")

    intro = spawn.get("intro")
    if intro is None:
        return
    if not isinstance(intro, list):
        error("spawn_on_start.intro must be a list of beats ({text, after, pace}), told in order before it arrives")
        return
    for beat_index, beat in enumerate(intro):
        where = f"spawn_on_start.intro[{beat_index}]"
        if not isinstance(beat, dict):
            error(f"{where} must be an object ({{text, after, pace}})")
            continue
        for key in beat:
            if key not in _INTRO_BEAT_KEYS:
                error(f"{where}.{key} is not read (known: {', '.join(_INTRO_BEAT_KEYS)})")
        if not isinstance(beat.get("text"), str) or not beat.get("text", "").strip():
            error(f"{where}.text must be the words to tell")
        if "after" in beat:
            after = beat["after"]
            if isinstance(after, bool) or not isinstance(after, (int, float)) or not 0 <= after <= 600:
                error(f"{where}.after must be a number of seconds from 0 to 600 (the wait after the beat before)")
        if beat.get("pace") not in (None, "instant") and pacing.resolve_pace(beat.get("pace")) is None:
            error(
                f"{where}.pace '{beat.get('pace')}' is not a pace (a name -- {', '.join(pacing.TEXT_PACES)} -- "
                f"or characters per second from {pacing.PACE_RANGE[0]} to {pacing.PACE_RANGE[1]})"
            )


def _validate_quest_stages(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Every stage must say what it is waiting for.

    A stage with neither `objective` nor `objectives_any` has no route to
    satisfaction, and `QuestManager.get_active_objectives` returns an empty list
    for it -- so the quest stops there forever. Nothing used to report it: the
    editor's quest inspector wrote exactly that shape (`type`, `target`, `count`,
    `next` at stage level) and content validation passed with zero errors, which
    made a broken quest look finished. The world editor was fixed to write
    `objective`; this is the engine refusing to accept a stage without one.
    """
    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    room_refs: set[str] = set()
    for region_path in sorted((content_root / "regions").glob("*.json")):
        region = _load_json(region_path, issues, "region definitions")
        if isinstance(region, dict) and isinstance(region.get("rooms"), dict):
            region_id = str(region.get("region_id", region_path.stem)).strip()
            room_refs.update(f"{region_id}:{room_id}" for room_id in region["rooms"])

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                issues.append(ContentSetIssue(
                    "error", str(quests_path),
                    f"quest '{quest_id}' stage {index} must be an object",
                ))
                continue
            _validate_stage_fields(content_root, quests_path, quest_id, index, stage, issues, npc_ids, room_refs)
            if _stage_objectives(stage):
                continue
            unknown = sorted(
                key for key in stage
                if key in ("type", "target", "count", "next", "id")
            )
            hint = (
                " It carries %s, which is not a stage field the engine reads."
                % ", ".join(unknown)
            ) if unknown else ""
            issues.append(ContentSetIssue(
                "error", str(quests_path),
                f"quest '{quest_id}' stage {index} declares neither 'objective' nor "
                f"'objectives_any', so nothing can satisfy it.{hint}",
            ))


def _validate_instance_quests(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`quests/instances.json`: templates `QuestGenerator.generate_instance_quest` builds from.

    Every failure here was silent or a crash at generation time: a template with
    no target creatures or no existing entry region is never offered; an
    objective other than `clear_region` is accepted but never completes; and a
    reversed `min_rooms`/`max_rooms` or `target_count` range, or an empty room-name
    pool, raises inside `random` while the board is being filled.
    """
    path = content_root / "quests" / "instances.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "instance quest templates")
    if payload is None:
        return
    source = str(path)
    if not isinstance(payload, dict):
        issues.append(ContentSetIssue("error", source, "instances.json must be an object of instance quest templates"))
        return
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    region_ids = _knowledge_region_ids(content_root, issues)
    other_quest_ids: set[str] = set()
    for other in ("quests.json", "sagas.json"):
        other_payload = _load_json(content_root / "quests" / other, [], "quest definitions") if (content_root / "quests" / other).is_file() else None
        if isinstance(other_payload, dict):
            other_quest_ids |= {str(key) for key in other_payload if not str(key).startswith("_")}

    def positive_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 1

    def npc_ref(value: Any, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            issues.append(ContentSetIssue("error", source, f"{label} must be a non-empty string"))
        elif value not in npc_ids:
            issues.append(ContentSetIssue("error", source, f"{label} references missing NPC template '{value}'"))

    for template_id, template in payload.items():
        if str(template_id).startswith("_"):
            continue
        label = f"instance quest '{template_id}'"
        if not isinstance(template, dict):
            issues.append(ContentSetIssue("error", source, f"{label} must be an object"))
            continue
        if template_id in other_quest_ids:
            issues.append(ContentSetIssue(
                "error", source,
                f"{label} is also declared in quests.json or sagas.json; the loader keeps only one of them",
            ))
        if template.get("type") != "instance":
            issues.append(ContentSetIssue(
                "error", source,
                f"{label}.type must be 'instance' (only those are generated; other quests belong in quests.json)",
            ))
        if "level" in template and not positive_int(template["level"]):
            issues.append(ContentSetIssue("error", source, f"{label}.level must be an integer of at least 1"))
        if "giver_npc_template_id" in template:
            npc_ref(template["giver_npc_template_id"], f"{label}.giver_npc_template_id")

        if "possible_entry_regions" in template:
            regions = template["possible_entry_regions"]
            if not isinstance(regions, list) or not regions or any(not isinstance(r, str) or not r.strip() for r in regions):
                issues.append(ContentSetIssue("error", source, f"{label}.possible_entry_regions must be a non-empty array of region ids"))
            else:
                for region in regions:
                    if region_ids and region not in region_ids:
                        issues.append(ContentSetIssue("error", source, f"{label}.possible_entry_regions references missing region '{region}'"))

        rewards = template.get("rewards")
        if rewards is not None:
            if not isinstance(rewards, dict):
                issues.append(ContentSetIssue("error", source, f"{label}.rewards must be an object"))
            else:
                for key in ("xp", "gold"):
                    value = rewards.get(key)
                    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                        issues.append(ContentSetIssue("error", source, f"{label}.rewards.{key} must be a non-negative integer"))

        objective = template.get("objective")
        if not isinstance(objective, dict):
            issues.append(ContentSetIssue("error", source, f"{label}.objective must be an object"))
        else:
            if objective.get("type") != "clear_region":
                issues.append(ContentSetIssue(
                    "error", source,
                    f"{label}.objective.type must be 'clear_region' (the only instance objective the quest tracker completes)",
                ))
            targets = objective.get("possible_target_template_ids")
            if not isinstance(targets, list) or not targets:
                issues.append(ContentSetIssue(
                    "error", source,
                    f"{label}.objective.possible_target_template_ids must be a non-empty array; without one the template is never offered",
                ))
            else:
                for index, target in enumerate(targets):
                    npc_ref(target, f"{label}.objective.possible_target_template_ids[{index}]")
            if "completion_npc_template_id" in objective:
                npc_ref(objective["completion_npc_template_id"], f"{label}.objective.completion_npc_template_id")

        layout = template.get("layout_generation_config", {})
        if not isinstance(layout, dict):
            issues.append(ContentSetIssue("error", source, f"{label}.layout_generation_config must be an object"))
            continue
        layout_label = f"{label}.layout_generation_config"
        for key in ("region_name", "region_description"):
            if key in layout and (not isinstance(layout[key], str) or not layout[key].strip()):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.{key} must be a non-empty string"))
        min_rooms = layout.get("min_rooms", 3)
        max_rooms = layout.get("max_rooms", 7)
        if not positive_int(min_rooms) or not positive_int(max_rooms):
            issues.append(ContentSetIssue("error", source, f"{layout_label}.min_rooms and max_rooms must be integers of at least 1"))
        elif min_rooms > max_rooms:
            issues.append(ContentSetIssue("error", source, f"{layout_label}.min_rooms ({min_rooms}) is greater than max_rooms ({max_rooms})"))
        if "possible_room_names" in layout:
            names = layout["possible_room_names"]
            if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n.strip() for n in names):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.possible_room_names must be a non-empty array of strings"))
        if "target_count" in layout:
            count = layout["target_count"]
            if not (isinstance(count, list) and len(count) == 2 and all(positive_int(n) for n in count)):
                issues.append(ContentSetIssue("error", source, f"{layout_label}.target_count must be [min, max], two integers of at least 1"))
            elif count[0] > count[1]:
                issues.append(ContentSetIssue("error", source, f"{layout_label}.target_count minimum ({count[0]}) is greater than its maximum ({count[1]})"))


FIELD_POLARITIES = ("positive", "neutral", "negative")
_FIELD_INTERACTION_KEYS = ("fallback_positive_suppresses_negative", "default_field_id", "polarities", "pairwise_rules")


def _validate_field_interactions(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`world/field_interactions.json` (`headless/field_fx.py::_load_field_interaction_config`).

    The loader forgives everything: an unreadable file, an unknown top-level
    key, a polarity outside the three it knows and a non-numeric coefficient are
    all dropped without a word, and an out-of-range coefficient is clamped. Keys
    are lower-cased on read, so a field id written any other way only works by
    accident. Its presence alone turns the ambient field system on.
    """
    path = content_root / "world" / "field_interactions.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "field interactions")
    if payload is None:
        return
    source = str(path)
    if not isinstance(payload, dict):
        issues.append(ContentSetIssue("error", source, "field_interactions.json must be an object"))
        return

    def field_id_ok(value: Any, label: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            issues.append(ContentSetIssue("error", source, f"{label} must be a non-empty field id"))
            return False
        if value != value.strip().lower():
            issues.append(ContentSetIssue("error", source, f"{label} '{value}' must be lower-case with no surrounding spaces (the engine reads it as '{value.strip().lower()}')"))
            return False
        return True

    def coefficient_ok(value: Any, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            issues.append(ContentSetIssue("error", source, f"{label} must be a number from 0 to 1"))

    for key in payload:
        if not str(key).startswith("_") and key not in _FIELD_INTERACTION_KEYS:
            issues.append(ContentSetIssue("error", source, f"'{key}' is not a field-interaction setting (known: {', '.join(_FIELD_INTERACTION_KEYS)})"))

    if "fallback_positive_suppresses_negative" in payload:
        coefficient_ok(payload["fallback_positive_suppresses_negative"], "fallback_positive_suppresses_negative")

    declared: set[str] = set()
    polarities = payload.get("polarities", {})
    if not isinstance(polarities, dict):
        issues.append(ContentSetIssue("error", source, "polarities must be an object of field id -> polarity"))
    else:
        for field_id, polarity in polarities.items():
            if field_id_ok(field_id, "polarities key"):
                declared.add(field_id)
            if polarity not in FIELD_POLARITIES:
                issues.append(ContentSetIssue("error", source, f"polarities.{field_id} must be one of {', '.join(FIELD_POLARITIES)}"))

    default_field_id = payload.get("default_field_id")
    if default_field_id is not None and field_id_ok(default_field_id, "default_field_id") and declared and default_field_id not in declared:
        issues.append(ContentSetIssue(
            "warning", source,
            f"default_field_id '{default_field_id}' has no declared polarity, so it is treated as neutral",
        ))

    rules = payload.get("pairwise_rules", {})
    if not isinstance(rules, dict):
        issues.append(ContentSetIssue("error", source, "pairwise_rules must be an object of source field -> {target field: coefficient}"))
        return
    for source_id, targets in rules.items():
        field_id_ok(source_id, "pairwise_rules key")
        if not isinstance(targets, dict) or not targets:
            issues.append(ContentSetIssue("error", source, f"pairwise_rules.{source_id} must be a non-empty object of target field -> coefficient"))
            continue
        for target_id, coefficient in targets.items():
            label = f"pairwise_rules.{source_id}.{target_id}"
            field_id_ok(target_id, f"pairwise_rules.{source_id} key")
            coefficient_ok(coefficient, label)
            if target_id == source_id:
                issues.append(ContentSetIssue("error", source, f"{label}: a field never suppresses itself, so this rule never applies"))
            for named in (source_id, target_id):
                if declared and named not in declared:
                    issues.append(ContentSetIssue("warning", source, f"{label} names '{named}', which has no declared polarity"))


def _validate_quest_choice_outcomes(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """A branching objective must say where each of its outcomes leads.

    `negotiate` and `dialogue_choice` objectives resolve to one of several
    authored outcomes, and each outcome decides what happens next. Omitting
    `next_stage` used to fall back to "the stage after this one", which is a
    silent *lie* whenever the next stage is the violent option: a successful
    truce in `quest_bandit_lieutenant` advanced to "Kill the Lieutenant", and
    the campaign's PEACEFUL_SUCCESS transition on that node could never fire.

    So: every outcome must declare `next_stage` (move on), or `complete: true`
    (this ends the quest). Anything else is an authoring error rather than a
    default the author never chose.
    """
    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            for objective in _stage_objectives(stage):
                if str(objective.get("type", "")) not in ("negotiate", "dialogue_choice"):
                    continue
                choices = objective.get("choices")
                label = f"quest '{quest_id}' stage {index} ({objective.get('type')})"
                if not isinstance(choices, dict) or not choices:
                    issues.append(ContentSetIssue(
                        "error", str(quests_path),
                        f"{label} has no choices to resolve",
                    ))
                    continue
                for outcome, branch in choices.items():
                    where = f"{label} outcome '{outcome}'"
                    if not isinstance(branch, dict):
                        issues.append(ContentSetIssue("error", str(quests_path), f"{where} must be an object"))
                        continue
                    next_stage = branch.get("next_stage")
                    completes = bool(branch.get("complete", False))
                    if next_stage is None and not completes:
                        issues.append(ContentSetIssue(
                            "error", str(quests_path),
                            f"{where} must declare next_stage or complete: true -- "
                            f"otherwise it silently advances to the next stage",
                        ))
                        continue
                    if next_stage is not None:
                        if isinstance(next_stage, bool) or not isinstance(next_stage, int):
                            issues.append(ContentSetIssue(
                                "error", str(quests_path), f"{where}.next_stage must be an integer",
                            ))
                        elif not (0 <= next_stage <= len(stages)):
                            issues.append(ContentSetIssue(
                                "error", str(quests_path),
                                f"{where}.next_stage {next_stage} is outside this quest's "
                                f"{len(stages)} stages",
                            ))


def _stage_objectives(stage: dict) -> list[dict]:
    """Every objective a stage routes through (compact `objective` or
    `objectives_any`)."""
    found: list[dict] = []
    objective = stage.get("objective")
    if isinstance(objective, dict):
        found.append(objective)
    alternatives = stage.get("objectives_any")
    if isinstance(alternatives, list):
        found.extend(entry for entry in alternatives if isinstance(entry, dict))
    return found


def _load_recipes(content_root: Path, issues: list[ContentSetIssue]) -> dict[str, dict]:
    recipes: dict[str, dict] = {}
    crafting_dir = content_root / "crafting"
    if not crafting_dir.is_dir():
        return recipes
    for path in sorted(crafting_dir.glob("*.json")):
        payload = _load_json(path, issues, "crafting recipes")
        if not isinstance(payload, dict):
            continue
        for recipe_id, recipe in payload.items():
            if isinstance(recipe, dict) and not str(recipe_id).startswith("_"):
                recipes[str(recipe_id)] = recipe
    return recipes


def _validate_new_quest_objective_types(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """Validate the five reused-infrastructure objective types added in P6:
    relationship, discover_n, craft_quality, gather_types, deliver_multi.

    Each reuses an existing tracked value (relationship score, advancement
    ledger, recipe quality tiers, resource item ids, NPC templates) rather
    than inventing new player state, so validation is mostly "does this
    reference something real."
    """
    from engine.core.advancement import KNOWN_ENTRY_KINDS

    quests_path = content_root / "quests" / "quests.json"
    if not quests_path.is_file():
        return
    payload = _load_json(quests_path, issues, "quest definitions")
    if not isinstance(payload, dict):
        return

    item_ids = _load_definition_ids(content_root / "items", "item definitions", issues)
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    recipes = _load_recipes(content_root, issues)

    for quest_id, quest in payload.items():
        if str(quest_id).startswith("_") or not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if not isinstance(stages, list):
            continue
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            for objective in _stage_objectives(stage):
                obj_type = str(objective.get("type", ""))
                label = f"quest '{quest_id}' stage {index} ({obj_type})"

                if obj_type == "relationship":
                    target = objective.get("target_npc_template_id")
                    if not isinstance(target, str) or target not in npc_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.target_npc_template_id references a missing NPC template"))
                    score = objective.get("required_score")
                    if isinstance(score, bool) or not isinstance(score, int):
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_score must be an integer"))

                elif obj_type == "discover_n":
                    kind = objective.get("kind")
                    if kind not in KNOWN_ENTRY_KINDS:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.kind must be one of {sorted(KNOWN_ENTRY_KINDS)}"))
                    count = objective.get("required_count")
                    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_count must be a positive integer"))

                elif obj_type == "craft_quality":
                    recipe_id = objective.get("recipe_id")
                    recipe = recipes.get(recipe_id) if isinstance(recipe_id, str) else None
                    if recipe is None:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipe_id references a missing recipe"))
                        continue
                    required_quality_id = objective.get("required_quality_id")
                    tiers = recipe.get("quality_tiers", [])
                    tier_ids = {tier.get("id") for tier in tiers if isinstance(tier, dict)}
                    if not isinstance(required_quality_id, str) or required_quality_id not in tier_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_quality_id must name one of {recipe_id}'s quality_tiers ids"))

                elif obj_type == "gather_types":
                    required_ids = objective.get("required_item_ids")
                    if not isinstance(required_ids, list) or not required_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_item_ids must be a non-empty array"))
                    else:
                        for item_id in required_ids:
                            if not isinstance(item_id, str) or item_id not in item_ids:
                                issues.append(ContentSetIssue("error", str(quests_path), f"{label}.required_item_ids references a missing item template: {item_id!r}"))

                elif obj_type == "deliver_multi":
                    item_template_id = objective.get("item_template_id")
                    if not isinstance(item_template_id, str) or item_template_id not in item_ids:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.item_template_id references a missing item template"))
                    recipients = objective.get("recipients")
                    if not isinstance(recipients, list) or len(recipients) < 2:
                        issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipients must be an array of at least 2 entries"))
                    else:
                        for r_index, recipient in enumerate(recipients):
                            if not isinstance(recipient, dict) or recipient.get("template_id") not in npc_ids:
                                issues.append(ContentSetIssue("error", str(quests_path), f"{label}.recipients[{r_index}].template_id references a missing NPC template"))
