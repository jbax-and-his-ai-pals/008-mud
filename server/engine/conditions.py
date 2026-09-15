"""One condition language for dialogue, titles, and quest availability.

Three systems need to ask the same question -- "does this apply to this player
right now?" -- and needed the same answer. Rather than three bespoke checks,
they share this evaluator.

A condition is data:

    {"kind": "has_item", "item_id": "item_iron_ingot", "quantity": 2}
    {"kind": "skill_at_least", "skill": "crafting", "value": 3}
    {"kind": "spell_known", "spell_id": "minor_heal"}
    {"kind": "relationship_at_least", "npc_id": "village_elder", "value": 10}
    {"kind": "quest_completed", "quest_id": "quest_scout_forest"}
    {"kind": "discovery", "discovery_id": "rose_quartz"}
    {"kind": "visited_region", "region_id": "forest"}
    {"kind": "level_at_least", "value": 5}
    {"kind": "title_earned", "title_id": "cleric"}
    {"kind": "background", "background_id": "scholar"}
    {"kind": "flag", "flag": "met_the_king"}

Composites:

    {"all": [ ... ]}     every child must pass
    {"any": [ ... ]}     at least one child must pass
    {"not": { ... }}     the child must fail

An empty or missing condition is satisfied -- a title with no gate is one
everyone has, which is the authoring default rather than a special case.

Unknown *kinds* are an authoring error: they fail closed and are reported, so a
typo in content cannot silently open a gate. That is the opposite of the
entitlement guard's old fail-open behaviour, and deliberately so: this
evaluator gates content a player has not earned, so failing closed is the only
safe direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# Condition kinds this evaluator understands. Content referencing anything else
# is reported rather than ignored.
KNOWN_KINDS = frozenset({
    "has_item", "skill_at_least", "spell_known", "relationship_at_least",
    "quest_completed", "quest_active", "discovery", "visited_region",
    "level_at_least", "title_earned", "background", "flag", "knows_recipe",
    "gold_at_least", "in_region", "time_of_day", "season",
})


@dataclass
class Evaluation:
    """The result of evaluating a condition, with the reason it failed."""

    satisfied: bool
    reasons: List[str] = field(default_factory=list)
    unknown_kinds: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.satisfied


def _number(value: Any, default: float = 0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _npc_relationship(player, npc_id: str) -> int:
    """Trust toward an NPC, by instance id or by template id.

    Authored conditions usually name a *template* ("village_elder") while the
    relationship ledger is keyed by the live NPC's instance. Both are tried, in
    that order, mirroring how quest rewards and board gates already resolve it.
    """
    from engine.social.relationships import relationship_key

    relationships = getattr(player, "npc_relationships", None)
    if not isinstance(relationships, dict):
        return 0

    direct = relationships.get(npc_id)
    if isinstance(direct, (int, float)):
        return int(direct)

    world = getattr(player, "world", None)
    if world is None:
        return 0
    for npc in getattr(world, "npcs", {}).values():
        if getattr(npc, "template_id", None) != npc_id:
            continue
        value = relationships.get(relationship_key(npc))
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _player_flag(player, flag: str) -> bool:
    for source in (
        getattr(player, "flags", None),
        getattr(getattr(player, "runtime_state", None), "flags", None),
    ):
        if isinstance(source, dict) and source.get(flag):
            return True
    return False


def _knows_recipe(player, recipe_id: str) -> bool:
    known = getattr(player, "known_recipe_ids", None)
    return bool(known) and recipe_id in known


def _visited_region(player, region_id: str) -> bool:
    """First-entry is recorded by the advancement ledger, so that is the record
    of where a player has actually been."""
    world = getattr(player, "world", None)
    server = getattr(world, "server", None) if world is not None else None
    manager = getattr(server, "advancement_manager", None) if server is not None else None
    if manager is None:
        return getattr(player, "current_region_id", None) == region_id
    return bool(manager.has_entry(player, "region:%s" % region_id))


def _current_time_context(player) -> Dict[str, str]:
    world = getattr(player, "world", None)
    time_manager = getattr(getattr(world, "game", None), "time_manager", None)
    data = getattr(time_manager, "time_data", None)
    if not isinstance(data, dict):
        return {}
    return {
        "time_of_day": str(data.get("period", data.get("time_of_day", "")) or ""),
        "season": str(data.get("season", "") or ""),
    }


def evaluate(condition: Any, player: Any) -> Evaluation:
    """Evaluate `condition` for `player`. A falsy condition is satisfied."""
    unknown: List[str] = []
    reasons: List[str] = []

    def walk(node: Any) -> bool:
        if node is None or node == {} or node == []:
            return True
        if isinstance(node, list):
            return all(walk(child) for child in node)
        if not isinstance(node, dict):
            # A condition that is neither a mapping nor a list is malformed;
            # refuse rather than treat a stray string as "open".
            reasons.append("malformed condition %r" % (node,))
            return False

        if "all" in node:
            return all(walk(child) for child in (node.get("all") or []))
        if "any" in node:
            children = node.get("any") or []
            return any(walk(child) for child in children) if children else True
        if "not" in node:
            return not walk(node.get("not"))

        kind = str(node.get("kind", "")).strip()
        if not kind:
            reasons.append("condition has no 'kind'")
            return False
        if kind not in KNOWN_KINDS:
            # Fail closed and surface it: an unrecognised kind is a content bug,
            # and treating it as satisfied would silently unlock gated content.
            unknown.append(kind)
            reasons.append("unknown condition kind %r" % kind)
            return False

        return _evaluate_kind(kind, node, player, reasons)

    satisfied = walk(condition)
    return Evaluation(satisfied=satisfied, reasons=reasons, unknown_kinds=unknown)


def _evaluate_kind(kind: str, node: Dict[str, Any], player: Any, reasons: List[str]) -> bool:
    if player is None:
        reasons.append("no player")
        return False

    if kind == "has_item":
        item_id = str(node.get("item_id", "")).strip()
        quantity = int(_number(node.get("quantity", 1), 1))
        inventory = getattr(player, "inventory", None)
        have = inventory.count_item(item_id) if inventory is not None else 0
        if have < quantity:
            reasons.append("needs %d x %s (has %d)" % (quantity, item_id, have))
            return False
        return True

    if kind == "knows_recipe":
        recipe_id = str(node.get("recipe_id", "")).strip()
        if not _knows_recipe(player, recipe_id):
            reasons.append("has not learned recipe %s" % recipe_id)
            return False
        return True

    if kind == "skill_at_least":
        skill = str(node.get("skill", "")).strip()
        value = int(_number(node.get("value", 1), 1))
        have = player.get_skill_level(skill) if hasattr(player, "get_skill_level") else 0
        if have < value:
            reasons.append("needs %s %d (has %d)" % (skill, value, have))
            return False
        return True

    if kind == "spell_known":
        spell_id = str(node.get("spell_id", "")).strip()
        magic = getattr(getattr(player, "runtime_state", None), "magic", None)
        known = getattr(magic, "known_spells", None) or set()
        if spell_id not in known:
            reasons.append("does not know spell %s" % spell_id)
            return False
        return True

    if kind == "relationship_at_least":
        npc_id = str(node.get("npc_id", "")).strip()
        value = int(_number(node.get("value", 1), 1))
        have = _npc_relationship(player, npc_id)
        if have < value:
            reasons.append("needs %d trust with %s (has %d)" % (value, npc_id, have))
            return False
        return True

    if kind in ("quest_completed", "quest_active"):
        quest_id = str(node.get("quest_id", "")).strip()
        quests = getattr(getattr(player, "runtime_state", None), "quests", None)
        completed = getattr(quests, "completed", None) or {}
        archived = getattr(quests, "archived", None) or {}
        active = getattr(quests, "active", None) or {}

        def matches(bucket: Dict[str, Any]) -> bool:
            if quest_id in bucket:
                return True
            for entry in bucket.values():
                if not isinstance(entry, dict):
                    continue
                if quest_id in (
                    str(entry.get("template_id", "")),
                    str(entry.get("quest_id", "")),
                    str(entry.get("title", "")),
                ):
                    return True
                # Instance ids are "<template>_<suffix>"; accept the prefix.
                if str(entry.get("instance_id", "")).startswith(quest_id):
                    return True
            return False

        if kind == "quest_completed":
            if not (matches(completed) or matches(archived)):
                reasons.append("has not completed %s" % quest_id)
                return False
        else:
            if not matches(active):
                reasons.append("%s is not active" % quest_id)
                return False
        return True

    if kind == "discovery":
        discovery_id = str(node.get("discovery_id", "")).strip()
        discoveries = getattr(player, "discoveries", None) or {}
        if discovery_id not in discoveries:
            reasons.append("has not found %s" % discovery_id)
            return False
        return True

    if kind == "visited_region":
        region_id = str(node.get("region_id", "")).strip()
        if not _visited_region(player, region_id):
            reasons.append("has not been to %s" % region_id)
            return False
        return True

    if kind == "in_region":
        region_id = str(node.get("region_id", "")).strip()
        if getattr(player, "current_region_id", None) != region_id:
            reasons.append("is not in %s" % region_id)
            return False
        return True

    if kind == "level_at_least":
        value = int(_number(node.get("value", 1), 1))
        progression = getattr(getattr(player, "runtime_state", None), "progression", None)
        level = int(getattr(progression, "level", 1) or 1)
        if level < value:
            reasons.append("needs level %d (is %d)" % (value, level))
            return False
        return True

    if kind == "gold_at_least":
        value = int(_number(node.get("value", 1), 1))
        gold = getattr(getattr(player, "runtime_state", None), "gold", 0) or 0
        if int(gold) < value:
            reasons.append("needs %d gold (has %d)" % (value, int(gold)))
            return False
        return True

    if kind == "title_earned":
        title_id = str(node.get("title_id", "")).strip()
        earned = getattr(player, "earned_titles", None) or set()
        if title_id not in earned:
            reasons.append("has not earned the %s title" % title_id)
            return False
        return True

    if kind == "background":
        wanted = str(node.get("background_id", "")).strip()
        have = str(getattr(player, "background_id", "") or "")
        if have != wanted:
            reasons.append("background is %r not %r" % (have, wanted))
            return False
        return True

    if kind == "flag":
        flag = str(node.get("flag", "")).strip()
        if not _player_flag(player, flag):
            reasons.append("flag %s is not set" % flag)
            return False
        return True

    if kind in ("time_of_day", "season"):
        context = _current_time_context(player)
        wanted = str(node.get("value", "")).strip()
        have = context.get(kind, "")
        if have != wanted:
            reasons.append("%s is %r not %r" % (kind, have, wanted))
            return False
        return True

    reasons.append("unhandled condition kind %r" % kind)
    return False


def explain(condition: Any, player: Any) -> str:
    """A short, player-safe sentence for why a gate is closed."""
    result = evaluate(condition, player)
    if result.satisfied:
        return ""
    if result.reasons:
        return result.reasons[0]
    return "the requirements are not met yet"
