"""Content-neutrality validator.

The engine is supposed to stay content-neutral: names, ids, values, and lore
live in content sets, while `server/engine` holds mechanics. A content id
appearing as a string literal in engine code is a leak -- it means a different
content set cannot rename or replace that thing without an engine change.

This check extracts every content identifier from a content set and reports any
that appear as string literals in engine source.

Scope notes:
  - Only *content* ids are checked (item/spell/NPC/quest/recipe/region ids and
    authored skill names). Abstract vocabulary the engine legitimately owns --
    faction names, behaviour types, damage types -- is deliberately not checked
    here, because the engine defines those as its own shared model. Abstract
    faction values are listed in `engine/config/config_world.py` on purpose.
  - Schema keys (`item_id`, `template_id`, ...) are ignored; they are field
    names, not content.
  - Debug/GM modules are reported separately, since a debug command naming a
    debug item is far less serious than a gameplay path naming a real one.

Usage:
    python toolkit/content_neutrality_validator.py content_sets/fantasy_frontier
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class NeutralityIssue:
    severity: str
    path: str
    line: int
    content_id: str
    source: str


# Field names and other schema vocabulary that happens to look like an id.
_SCHEMA_KEYS = frozenset({
    "item_id", "item_ids", "item_name", "item_instance_id", "item_template_id",
    "item_to_deliver_name", "item_to_deliver_description", "item_name_plural",
    "item_tags", "item_type", "result_item_id", "resource_item_id",
    "spell_id", "spell_name", "npc_id", "npc_name", "npc_template_id",
    "obj_id", "template_id", "giver_npc_id", "turn_in_id", "giver_template_id",
    "recipient_template_id", "target_template_id", "possible_target_template_ids",
    "quest_id", "quest_template_id", "region_id", "room_id", "player_id",
    "session_id", "container_id", "recipe_id", "node_id", "faction_id",
    "skill_id", "effect_id", "key_id", "chest_id", "field_id", "cell_id",
    "owner_id", "leader_player_id", "member_player_ids", "instance_id",
    "giver_instance_id", "target_region", "target_room", "target_node_id",
    "start_node_id", "quest_ids", "campaign_id", "collection_id",
    "discovery_id", "item", "items", "name", "type", "id", "description",
})

# Abstract engine-owned vocabulary: not content identifiers, so not leaks.
# Faction and damage-type values are the engine's shared model; a content set
# *uses* them rather than *defining* them.
_ENGINE_VOCABULARY = frozenset({
    "hostile", "friendly", "neutral", "player", "player_minion",
    "physical", "magical", "damage", "heal", "buff", "debuff", "summon",
    "cleanse", "remove_curse", "life_tap", "utility",
})

# NPC behaviour types the engine's AI dispatcher switches on. These form a
# closed set owned by the engine: `engine/npcs/ai/dispatcher.py` routes each
# one to a specific AI routine, so content selects from them rather than
# naming them. (Noted in ROADMAP P2 as worth documenting explicitly.)
_ENGINE_BEHAVIOUR_TYPES = frozenset({
    "aggressive", "stationary", "wanderer", "scheduled", "patrol",
    "healer", "minion", "defensive", "passive", "guard",
})

# Ruleset *field* names that sit alongside authored ids and therefore look like
# one. `skills.stat_bonuses` is a schema field, not a skill.
_RULESET_SCHEMA_FIELDS = frozenset({
    "stat_bonuses", "per_point", "per_level", "default_item_id",
    "additional_blocked_command_names", "authored_board_templates",
    "text_templates", "excluded_name_keywords", "plantable_crops",
    "starting_skills", "player_defaults", "player_class",
})

# Debug/GM modules are reported at lower severity: they are not player paths.
_DEBUG_PATH_MARKERS = ("/debug/", "debug_", "/commands/debug")

# Content-neutrality leaks that are known and scheduled for cleanup in ROADMAP
# P2. Listed explicitly rather than via an error-count threshold so that a *new*
# leak in the same file still fails the gate, and so the list itself documents
# the remaining work.
#
# All P2 leaks are now fixed, so this list is empty. That is the point: it is
# the gate's job to stay empty. If a leak is ever tolerated again, add it here
# with a comment explaining why, and it will show up in the gate's output as
# [KNOWN] rather than silently passing.
KNOWN_NEUTRALITY_LEAKS: tuple[tuple[str, str], ...] = ()


def _is_known_leak(path: str, content_id: str) -> bool:
    normalized = str(path).replace("\\", "/")
    return (normalized, content_id) in KNOWN_NEUTRALITY_LEAKS


# JSON structural vocabulary: keys that describe *shape* rather than name
# content, and which therefore appear in engine code legitimately.
_STRUCTURAL_KEYS = frozenset({
    "properties", "rooms", "exits", "spawner", "themes", "placeholders",
    "items", "nodes", "stages", "objectives", "transitions", "effects",
    "ingredients", "rewards", "bonuses", "dialog", "loot_table", "contains",
    "monster_types", "level_range", "room_names", "room_descriptions",
    "name_templates", "quality_tiers", "familiarity_milestones", "choices",
    "conditions", "overrides", "patrol_points", "usable_spells", "stats",
    "equipment", "inventory", "spells", "skills", "defaults", "caps",
})

# A real content definition carries at least one of these, which is what
# separates `item_iron_sword: {type: Weapon, name: ...}` from
# `spawner: {monster_types: ...}`.
_DEFINITION_MARKERS = frozenset({
    "name", "type", "description", "title", "category", "value", "weight",
    "health", "level", "mana_cost", "result_item_id", "ingredients",
})


def _collect_content_ids(content_root: Path) -> dict[str, str]:
    """id -> the content file that defines it.

    Only genuine *definitions* are collected. A top-level key whose value is a
    bag of structural fields (`spawner`, `properties`, `exits`) names part of a
    schema, not a piece of content, and the engine is entitled to reference it.
    """
    found: dict[str, str] = {}

    def looks_like_definition(key: str, value: dict) -> bool:
        if key in _STRUCTURAL_KEYS or key in _SCHEMA_KEYS:
            return False
        # Ids are authored lowercase-with-underscores by convention.
        if not key or key != key.lower() or " " in key:
            return False
        return bool(_DEFINITION_MARKERS & set(value.keys()))

    def absorb(directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if isinstance(key, str) and isinstance(value, dict):
                    if looks_like_definition(key, value):
                        found.setdefault(key, str(path))

    for sub in ("items", "magic", "npcs", "quests", "crafting", "regions"):
        absorb(content_root / sub)

    # Skill ids are authored under the ruleset.
    ruleset_path = content_root.parent / "rules" / "ruleset.json"
    if ruleset_path.is_file():
        try:
            ruleset = json.loads(ruleset_path.read_text(encoding="utf-8"))
        except Exception:
            ruleset = {}
        skills = ruleset.get("skills") if isinstance(ruleset, dict) else None
        if isinstance(skills, dict):
            for key, value in skills.items():
                if isinstance(key, str) and key and key == key.lower() and " " not in key:
                    found.setdefault(key, str(ruleset_path))
                if isinstance(value, dict) and isinstance(value.get("id"), str):
                    found.setdefault(value["id"], str(ruleset_path))

    return found


def _iter_engine_modules(engine_root: Path):
    for path in sorted(engine_root.rglob("*.py")):
        yield path


def _string_literals(path: Path) -> list[tuple[int, str, str]]:
    """(line, literal, source-line) for every plain string constant."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if not value or value in _SCHEMA_KEYS or value in _ENGINE_VOCABULARY:
                continue
            if value in _ENGINE_BEHAVIOUR_TYPES or value in _RULESET_SCHEMA_FIELDS:
                continue
            source = lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else ""
            out.append((node.lineno, value, source))
    return out


def validate(repo_root: Path, content_set: Path) -> list[NeutralityIssue]:
    content_root = content_set / "data"
    if not content_root.is_dir():
        content_root = content_set
    content_ids = _collect_content_ids(content_root)
    engine_root = repo_root / "server" / "engine"

    issues: list[NeutralityIssue] = []
    for path in _iter_engine_modules(engine_root):
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        is_debug = any(marker in "/" + rel for marker in _DEBUG_PATH_MARKERS)
        for line, literal, source in _string_literals(path):
            if literal not in content_ids:
                continue
            if _is_known_leak(rel, literal):
                issues.append(NeutralityIssue(
                    severity="known",
                    path=rel,
                    line=line,
                    content_id=literal,
                    source=source[:120],
                ))
                continue
            issues.append(NeutralityIssue(
                severity="warning" if is_debug else "error",
                path=rel,
                line=line,
                content_id=literal,
                source=source[:120],
            ))
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Report content ids hardcoded in engine code.")
    parser.add_argument("content_set", nargs="?", default="content_sets/fantasy_frontier",
                        help="Content-set directory to source ids from.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--max-errors", type=int, default=0,
                        help="Allowed error count before failing (default 0).")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    content_set = Path(args.content_set)
    if not content_set.is_absolute():
        content_set = repo_root / content_set
    if not content_set.exists():
        print(f"[ERROR] Content set not found: {content_set}")
        raise SystemExit(2)

    issues = validate(repo_root, content_set)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    known = [i for i in issues if i.severity == "known"]

    for issue in errors:
        print(f"[ERROR] {issue.path}:{issue.line} - engine hardcodes content id "
              f"'{issue.content_id}'  |  {issue.source}")
    for issue in warnings:
        print(f"[WARN]  {issue.path}:{issue.line} - debug module references content id "
              f"'{issue.content_id}'  |  {issue.source}")
    for issue in known:
        print(f"[KNOWN] {issue.path}:{issue.line} - '{issue.content_id}' "
              f"(listed in KNOWN_NEUTRALITY_LEAKS; see ROADMAP P2)")

    print(f"Content-neutrality issues: {len(issues)} (errors: {len(errors)}, "
          f"debug-only warnings: {len(warnings)}, known/scheduled: {len(known)})")
    raise SystemExit(1 if len(errors) > args.max_errors else 0)


if __name__ == "__main__":
    main()
