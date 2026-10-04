"""Knowledge topics.

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


def _knowledge_region_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    ids: set[str] = set()
    region_dir = content_root / "regions"
    if not region_dir.is_dir():
        return ids
    for path in sorted(region_dir.glob("*.json")):
        payload = _load_json(path, issues, "region definitions")
        if isinstance(payload, dict) and not isinstance(payload.get("themes"), dict):
            ids.add(str(payload.get("region_id", path.stem)).strip())
    return ids


def _knowledge_campaign_ids(content_root: Path, issues: list[ContentSetIssue]) -> set[str]:
    ids: set[str] = set()
    campaign_dir = content_root / "campaigns"
    if not campaign_dir.is_dir():
        return ids
    for path in sorted(campaign_dir.glob("*.json")):
        payload = _load_json(path, issues, "campaign definitions")
        if isinstance(payload, dict):
            ids.add(str(payload.get("campaign_id", path.stem)).strip())
    return ids


def _validate_knowledge_topics(content_root: Path, issues: list[ContentSetIssue]) -> None:
    """`data/knowledge/topics.json` (`engine/core/knowledge_manager.py`).

    A topic's own condition language is not `engine/conditions.py`'s
    `KNOWN_KINDS` -- `KnowledgeManager._check_conditions` is a separate, hand-
    rolled vocabulary keyed on the NPC being asked (`region_id`, `faction`,
    `template_id`) and on player/world state (`knowledge_state`,
    `campaign_state`, `campaign_outcome`, `quest_state`), and a response's
    `conditions` object may combine several of them at once (every key present
    must hold, the same as the flat `and` the manager evaluates). `effects`
    reuses the dialogue effect language exactly, so it is checked the same way
    `_validate_dialogue_content` checks a choice's effects.
    """
    from engine.core.knowledge_manager import (
        CAMPAIGN_STATES, KNOWLEDGE_CONDITION_KINDS, KNOWLEDGE_STATES, QUEST_STATES,
    )

    from engine.dialogue.effects import KNOWN_EFFECTS, effect_shape_issues

    path = content_root / "knowledge" / "topics.json"
    if not path.is_file():
        return
    payload = _load_json(path, issues, "knowledge topics")
    if not isinstance(payload, dict):
        if payload is not None:
            issues.append(ContentSetIssue("error", str(path), "topics.json must be an object"))
        return

    topic_ids = {str(key) for key in payload if not str(key).startswith("_")}
    npc_ids = _load_definition_ids(content_root / "npcs", "NPC definitions", issues)
    region_ids = _knowledge_region_ids(content_root, issues)
    campaign_ids = _knowledge_campaign_ids(content_root, issues)

    common_topics = payload.get("__common_topics__")
    if common_topics is not None:
        if not isinstance(common_topics, list):
            issues.append(ContentSetIssue("error", str(path), "__common_topics__ must be an array"))
        else:
            for topic_id in common_topics:
                if not isinstance(topic_id, str) or topic_id not in topic_ids:
                    issues.append(ContentSetIssue(
                        "error", str(path),
                        f"__common_topics__ names '{topic_id}', which is not a topic this file declares",
                    ))

    for topic_id, topic in payload.items():
        if str(topic_id).startswith("_"):
            continue
        label = f"topic '{topic_id}'"
        if not isinstance(topic, dict):
            issues.append(ContentSetIssue("error", str(path), f"{label} must be an object"))
            continue
        if "display_name" in topic and not isinstance(topic["display_name"], str):
            issues.append(ContentSetIssue("error", str(path), f"{label}.display_name must be a string"))
        if "keywords" in topic:
            keywords = topic["keywords"]
            if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
                issues.append(ContentSetIssue("error", str(path), f"{label}.keywords must be an array of strings"))

        responses = topic.get("responses", [])
        if not isinstance(responses, list):
            issues.append(ContentSetIssue("error", str(path), f"{label}.responses must be an array"))
            continue
        for index, response in enumerate(responses):
            resp_label = f"{label}.responses[{index}]"
            if not isinstance(response, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label} must be an object"))
                continue
            if not isinstance(response.get("text"), str) or not response["text"].strip():
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.text must be a non-empty string"))
            if "priority" in response and (isinstance(response["priority"], bool) or not isinstance(response["priority"], int)):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.priority must be an integer"))

            conditions = response.get("conditions", {})
            if not isinstance(conditions, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.conditions must be an object"))
            else:
                for key, value in conditions.items():
                    cond_label = f"{resp_label}.conditions.{key}"
                    if key not in KNOWLEDGE_CONDITION_KINDS:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{cond_label} is not a condition this engine checks "
                            f"(known: {', '.join(KNOWLEDGE_CONDITION_KINDS)})",
                        ))
                    elif key in ("region_id", "faction", "template_id"):
                        if not isinstance(value, str) or not value.strip():
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be a non-empty string"))
                        elif key == "region_id" and region_ids and value not in region_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} references an unknown region '{value}'"))
                        elif key == "template_id" and npc_ids and value not in npc_ids:
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} references an unknown NPC template '{value}'"))
                    elif key == "knowledge_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            topic_ref = value.get("topic_id")
                            if not isinstance(topic_ref, str) or topic_ref not in topic_ids:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.topic_id must name a topic this file declares"))
                            if value.get("state") not in KNOWLEDGE_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(KNOWLEDGE_STATES)}"))
                    elif key == "campaign_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            campaign_ref = value.get("campaign_id")
                            if not isinstance(campaign_ref, str) or (campaign_ids and campaign_ref not in campaign_ids):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.campaign_id references an unknown campaign"))
                            if value.get("state") not in CAMPAIGN_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(CAMPAIGN_STATES)}"))
                    elif key == "campaign_outcome":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            campaign_ref = value.get("campaign_id")
                            if not isinstance(campaign_ref, str) or (campaign_ids and campaign_ref not in campaign_ids):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.campaign_id references an unknown campaign"))
                            if not isinstance(value.get("outcome"), str) or not value["outcome"].strip():
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.outcome must be a non-empty string"))
                    elif key == "quest_state":
                        if not isinstance(value, dict):
                            issues.append(ContentSetIssue("error", str(path), f"{cond_label} must be an object"))
                        else:
                            if value.get("state") not in QUEST_STATES:
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.state must be one of {', '.join(QUEST_STATES)}"))
                            if "from_this_npc" in value and not isinstance(value["from_this_npc"], bool):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.from_this_npc must be a boolean"))
                            if "id_pattern" in value and not isinstance(value["id_pattern"], str):
                                issues.append(ContentSetIssue("error", str(path), f"{cond_label}.id_pattern must be a string"))

            effects = response.get("effects", {})
            if not isinstance(effects, dict):
                issues.append(ContentSetIssue("error", str(path), f"{resp_label}.effects must be an object"))
            else:
                for key in sorted(effects):
                    if key not in KNOWN_EFFECTS:
                        issues.append(ContentSetIssue(
                            "error", str(path),
                            f"{resp_label}.effects names '{key}', which is not an effect this engine knows "
                            f"(known: {', '.join(sorted(KNOWN_EFFECTS))})",
                        ))
                for problem in effect_shape_issues(effects):
                    issues.append(ContentSetIssue("error", str(path), f"{resp_label}.effects: {problem}"))
