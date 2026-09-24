"""What a line of dialogue *does*, in one place.

Choices and topic responses both carry an `effects` mapping, and both must mean
the same thing by it. Before this module the topics path
(`core/knowledge_manager.py`) had its own private effect handling covering five
keys; dialogue needed eleven. Rather than let the two drift, the interpreter
lives here and the topics path delegates to it.

Effect vocabulary (every key is optional; a mapping may carry several):

    start_quest       "quest_id"                     start an authored quest
    start_campaign    "campaign_id"
    advance_quest     "quest_id" | true              push a stage forward
    complete_quest    "quest_id" | true              finish it outright
    grant_recipe      "recipe_id" | ["a", "b"]       learn to craft
    grant_discovery   "discovery_id" | [...]
    teach_spell       "spell_id" | [...]
    give_item         "item_id" | {"item_id": qty} | [...]
    take_item         "item_id" | {"item_id": qty} | [...]
    give_gold         10
    adjust_relationship  {"npc": "template_id", "amount": 5}
    set_flag          "flag_name" | {"name": "flag_name", "value": true}
    reveal_exit       {"room": "town:cellar", "direction": "down"}
    move_npc          {"npc": "template_id", "region": "forest", "room": "clearing"}
    give_rewards      {"xp": 10, "gold": 5, "items": [...]}   structured bundle

Shorthands exist because most effects are one id and authors should not have to
write an object for that. Anything the interpreter does not recognise is
reported through `EffectReport.unknown`, and content validation refuses it
before the game runs -- a typo must not be a line that silently does nothing.

Player-facing lines come from here too, so every system that applies an effect
says the same sentence about it, and test mode can show the raw effect as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Every effect key this interpreter understands. Content validation imports it.
KNOWN_EFFECTS = frozenset({
    "start_quest", "start_campaign", "advance_quest", "complete_quest",
    "grant_recipe", "grant_discovery", "teach_spell",
    "give_item", "take_item", "give_gold", "adjust_relationship",
    "set_flag", "reveal_exit", "move_npc", "give_rewards",
})


@dataclass
class EffectReport:
    """What applying a set of effects did."""

    messages: List[str] = field(default_factory=list)
    applied: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)

    def message(self) -> str:
        return "\n".join(m for m in self.messages if m)

    def summary(self) -> str:
        """A compact mechanical line for test mode."""
        parts: List[str] = []
        if self.applied:
            parts.append("applied: %s" % ", ".join(self.applied))
        if self.failed:
            parts.append("failed: %s" % ", ".join(self.failed))
        if self.unknown:
            parts.append("unknown: %s" % ", ".join(self.unknown))
        return "; ".join(parts)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _entry_pairs(value: Any) -> List[tuple[str, int]]:
    """Normalise `"id"`, `["id", ...]`, `{"id": 2}` and `[{"item_id": ..}]`.

    Authors write all four shapes within a single session; making the
    interpreter accept them is cheaper than making every author remember which
    one this key wanted.
    """
    pairs: List[tuple[str, int]] = []
    for entry in _as_list(value):
        if isinstance(entry, str):
            if entry.strip():
                pairs.append((entry.strip(), 1))
            continue
        if isinstance(entry, dict):
            identifier = str(
                entry.get("item_id")
                or entry.get("id")
                or entry.get("recipe_id")
                or entry.get("spell_id")
                or entry.get("discovery_id")
                or entry.get("quest_id")
                or ""
            ).strip()
            if not identifier:
                continue
            try:
                quantity = max(1, int(entry.get("quantity", entry.get("count", 1)) or 1))
            except (TypeError, ValueError):
                quantity = 1
            pairs.append((identifier, quantity))
    return pairs


def _context_world(context: Dict[str, Any]):
    return context.get("world") or getattr(context.get("player"), "world", None)


def _context_npc(context: Dict[str, Any]):
    """Whoever is speaking: the conversation partner."""
    return context.get("npc") or context.get("speaker")


def _resolve_npc(context: Dict[str, Any], identifier: str):
    if not identifier:
        return _context_npc(context)
    world = _context_world(context)
    if world is None:
        return None
    direct = world.get_npc(identifier) if hasattr(world, "get_npc") else None
    if direct is not None:
        return direct
    for npc in getattr(world, "npcs", {}).values():
        if str(getattr(npc, "template_id", "")) == identifier:
            return npc
    return None


def _party_aware(server, player, hook: str) -> bool:
    return server is not None and hasattr(server, hook)


# -- individual effects -------------------------------------------------------

def _apply_quest_effects(effects: Dict[str, Any], player, world, report: EffectReport) -> None:
    quest_manager = getattr(world, "quest_manager", None) if world is not None else None

    for key, label in (("start_quest", "Started quest"), ("start_campaign", "Started campaign")):
        if key not in effects:
            continue
        manager = quest_manager if key == "start_quest" else getattr(world, "campaign_manager", None)
        if manager is None:
            report.failed.append("%s (no manager)" % key)
            continue
        for quest_id, _quantity in _entry_pairs(effects[key]):
            if key == "start_quest":
                started = manager.start_quest(quest_id, player)
                if started:
                    report.applied.append("%s %s" % (label.lower(), quest_id))
                    title = ""
                    active = getattr(getattr(player, "runtime_state", None), "quests", None)
                    # An active entry is keyed "<quest id>_<suffix>" and does
                    # not carry a template_id, so matching only on that field
                    # announced the raw id ("[Quest Accepted] quest_x") to
                    # the player instead of the quest's title.
                    for instance_id, entry in (getattr(active, "active", {}) or {}).items():
                        if str(entry.get("template_id", "")) == quest_id or str(instance_id).startswith(quest_id + "_"):
                            title = str(entry.get("title", "") or "")
                            break
                    report.messages.append("[Quest Accepted] %s" % (title or quest_id))
                else:
                    report.failed.append("start_quest %s" % quest_id)
            else:
                started = manager.start_campaign(quest_id, player)
                report.applied.append("%s %s" % (label.lower(), quest_id)) if started else report.failed.append(
                    "start_campaign %s" % quest_id
                )

    for key in ("advance_quest", "complete_quest"):
        if key not in effects:
            continue
        if quest_manager is None:
            report.failed.append("%s (no quest manager)" % key)
            continue
        targets = _quest_targets(effects[key], player, quest_manager)
        for quest_id in targets:
            if key == "advance_quest":
                dialogue = quest_manager.advance_quest_stage(player, quest_id)
                report.applied.append("advanced %s" % quest_id)
                if dialogue and dialogue != "QUEST_COMPLETE":
                    report.messages.append('"%s"' % dialogue)
            else:
                rewards = quest_manager.complete_quest(player, quest_id)
                report.applied.append("completed %s" % quest_id)
                report.messages.append("[Quest Complete] %s" % quest_id)
                if rewards:
                    report.messages.append(str(rewards))


def _quest_targets(value: Any, player, quest_manager) -> List[str]:
    """Quest ids to act on. `true` means "the quest this conversation is about"."""
    from engine.core.quests import manager as quest_manager_module  # noqa: F401  (typing only)

    if value is True:
        active = getattr(getattr(player, "runtime_state", None), "quests", None)
        return sorted((getattr(active, "active", {}) or {}).keys())
    return [identifier for identifier, _quantity in _entry_pairs(value)]


def _apply_learning_effects(effects: Dict[str, Any], player, report: EffectReport) -> None:
    for key, method, label in (
        ("grant_recipe", "learn_recipe", "Recipe"),
        ("teach_spell", "learn_spell", "Spell"),
        ("grant_discovery", None, "Discovery"),
    ):
        if key not in effects:
            continue
        for identifier, _quantity in _entry_pairs(effects[key]):
            if key == "grant_discovery":
                record = _record_discovery(player, identifier)
                if record:
                    report.applied.append("discovery %s" % identifier)
                else:
                    report.failed.append("grant_discovery %s" % identifier)
                continue
            learner = getattr(player, method, None)
            if not callable(learner):
                report.failed.append("%s (unsupported)" % key)
                continue
            learned, message = learner(identifier)
            if learned:
                report.applied.append("%s %s" % (key, identifier))
                report.messages.append(message)
            elif "already know" in str(message):
                # Not a failure: a second conversation saying the same thing is
                # normal, and the player should not be told off for listening.
                report.applied.append("%s %s (already known)" % (key, identifier))
            else:
                report.failed.append("%s %s: %s" % (key, identifier, message))


def _record_discovery(player, discovery_id: str) -> bool:
    discoveries = getattr(player, "discoveries", None)
    if not isinstance(discoveries, dict):
        return False
    if discovery_id in discoveries:
        return True
    discoveries[discovery_id] = {"discovery_id": discovery_id}
    # Recorded with the advancement ledger too, so a discovery grant pays for a
    # discovery made in conversation exactly as for one found by picking it up.
    from engine.core import advancement

    advancement.award(player, advancement.KIND_DISCOVERY, discovery_id)
    return True


def _apply_item_effects(effects: Dict[str, Any], player, world, report: EffectReport) -> None:
    from engine.items.item_factory import ItemFactory

    server = getattr(world, "server", None) if world is not None else None

    if "give_item" in effects:
        for item_id, quantity in _entry_pairs(effects["give_item"]):
            for _ in range(quantity):
                item = ItemFactory.create_item_from_template(item_id, world)
                if item is None:
                    report.failed.append("give_item %s (missing template)" % item_id)
                    break
                recipient = player
                if _party_aware(server, player, "distribute_party_loot"):
                    recipient, _note = server.distribute_party_loot(player, item)
                inventory = getattr(recipient, "inventory", None)
                if inventory is None:
                    report.failed.append("give_item %s (no inventory)" % item_id)
                    break
                inventory.add_item(item)
                report.applied.append("gave %s" % item_id)
                if recipient is player:
                    report.messages.append("You receive %s." % item.name)
                else:
                    report.messages.append("%s receives %s." % (recipient.name, item.name))

    if "take_item" in effects:
        for item_id, quantity in _entry_pairs(effects["take_item"]):
            inventory = getattr(player, "inventory", None)
            if inventory is None:
                report.failed.append("take_item %s (no inventory)" % item_id)
                continue
            if inventory.count_item(item_id) < quantity:
                report.failed.append("take_item %s (not carried)" % item_id)
                continue
            inventory.remove_item(item_id, quantity)
            report.applied.append("took %s" % item_id)

    if "give_gold" in effects:
        try:
            amount = int(effects.get("give_gold", 0) or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount > 0:
            if _party_aware(server, player, "grant_party_gold"):
                routing = str(server.grant_party_gold(player, amount))
                if routing:
                    report.messages.append("Rewards: %s" % routing)
                report.applied.append("gave %s gold" % amount)
            else:
                state = getattr(player, "runtime_state", None)
                if getattr(state, "gold", None) is not None:
                    state.gold = int(state.gold) + amount
                    report.applied.append("gave %s gold" % amount)
                    currency = "gold"
                    if world is not None and hasattr(world, "currency_name"):
                        currency = str(world.currency_name())
                    report.messages.append("You receive %d %s." % (amount, currency.capitalize()))
                else:
                    report.failed.append("give_gold %s (economy disabled)" % amount)


def _apply_relationship_effects(effects: Dict[str, Any], context, report: EffectReport) -> None:
    if "adjust_relationship" not in effects:
        return
    raw = effects["adjust_relationship"]
    player = context.get("player")
    world = _context_world(context)
    if isinstance(raw, dict):
        amount = raw.get("amount", raw.get("delta", 0))
        npc = _resolve_npc(context, str(raw.get("npc", "") or ""))
    else:
        amount = raw
        npc = _context_npc(context)
    try:
        amount = int(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if npc is None or amount == 0:
        report.failed.append("adjust_relationship (no npc or amount)")
        return

    from engine.social.relationships import apply_relationship_milestones, relationship_key

    relationships = getattr(player, "npc_relationships", None)
    if not isinstance(relationships, dict):
        report.failed.append("adjust_relationship (no relationship ledger)")
        return
    key = relationship_key(npc)
    before = int(relationships.get(key, 0) or 0)
    after = max(0, before + amount)
    relationships[key] = after
    report.applied.append("relationship %s %+d (%d -> %d)" % (key, amount, before, after))
    milestone_note = apply_relationship_milestones(player, npc, before, after, world)
    if milestone_note:
        report.messages.append(milestone_note)


def _apply_flag_effect(effects: Dict[str, Any], player, report: EffectReport) -> None:
    if "set_flag" not in effects:
        return
    raw = effects["set_flag"]
    if isinstance(raw, dict):
        name = str(raw.get("name", raw.get("flag", "")) or "").strip()
        value = raw.get("value", True)
    else:
        name = str(raw or "").strip()
        value = True
    if not name:
        report.failed.append("set_flag (no name)")
        return
    flags = getattr(player, "flags", None)
    if not isinstance(flags, dict):
        flags = {}
        setattr(player, "flags", flags)
    flags[name] = value
    report.applied.append("flag %s=%r" % (name, value))


def _apply_exit_effect(effects: Dict[str, Any], context, report: EffectReport) -> None:
    """Open a hidden exit, the same way a lever does.

    `properties.hidden_exits` on a room is a real traversable link that the room
    simply does not advertise; a lever adds it to `exits`, and this does the
    same for a conversation ("the guard unlocks the gate"). It is world state,
    not per-player state -- in a shared world, one player's conversation opens
    the way for everyone, exactly as one player's lever does.
    """
    if "reveal_exit" not in effects:
        return
    raw = effects["reveal_exit"]
    if not isinstance(raw, dict):
        report.failed.append("reveal_exit (must be an object)")
        return
    world = _context_world(context)
    room_ref = str(raw.get("room", "") or "").strip()
    direction = str(raw.get("direction", "") or "").strip().lower()
    if not room_ref or not direction:
        report.failed.append("reveal_exit (needs room and direction)")
        return
    region_id, _, room_id = room_ref.partition(":")
    if not room_id:
        region_id, room_id = str(getattr(context.get("player"), "current_region_id", "")), room_ref
    room = None
    if world is not None:
        region = world.get_region(region_id) if hasattr(world, "get_region") else None
        room = region.get_room(room_id) if region is not None else None
    if room is None:
        report.failed.append("reveal_exit (unknown room %s)" % room_ref)
        return
    hidden = (getattr(room, "properties", {}) or {}).get("hidden_exits", {})
    if direction not in hidden:
        report.failed.append("reveal_exit (%s has no hidden %s exit)" % (room_ref, direction))
        return
    room.exits[direction] = hidden[direction]
    report.applied.append("revealed %s %s" % (room_ref, direction))
    report.messages.append("A way %s opens." % direction)


def _apply_move_npc_effect(effects: Dict[str, Any], context, report: EffectReport) -> None:
    if "move_npc" not in effects:
        return
    raw = effects["move_npc"]
    if not isinstance(raw, dict):
        report.failed.append("move_npc (must be an object)")
        return
    npc = _resolve_npc(context, str(raw.get("npc", "") or ""))
    region_id = str(raw.get("region", "") or "").strip()
    room_id = str(raw.get("room", "") or "").strip()
    if npc is None or not region_id or not room_id:
        report.failed.append("move_npc (needs npc, region and room)")
        return
    npc.current_region_id = region_id
    npc.current_room_id = room_id
    report.applied.append("moved %s to %s:%s" % (getattr(npc, "name", "?"), region_id, room_id))


def _apply_reward_effect(effects: Dict[str, Any], player, world, report: EffectReport) -> None:
    rewards = effects.get("give_rewards")
    if not isinstance(rewards, dict):
        return
    server = getattr(world, "server", None) if world is not None else None
    if _party_aware(server, player, "grant_party_rewards"):
        text = str(server.grant_party_rewards(player, rewards))
        if text:
            report.messages.append(text)
        report.applied.append("rewards")
        return

    from engine.core.knowledge_manager import KnowledgeManager  # noqa: F401  (shared bundle logic)

    xp = int(rewards.get("xp", 0) or 0)
    gold = int(rewards.get("gold", 0) or 0)
    state = getattr(player, "runtime_state", None)
    if xp > 0 and getattr(state, "progression", None) is not None:
        player.gain_experience(xp)
        report.messages.append("You gain %d XP." % xp)
    if gold > 0 and getattr(state, "gold", None) is not None:
        state.gold = int(state.gold) + gold
        currency = "gold"
        if world is not None and hasattr(world, "currency_name"):
            currency = str(world.currency_name())
        report.messages.append("You receive %d %s." % (gold, currency.capitalize()))
    for entry in _as_list(rewards.get("items")):
        identifier = ""
        quantity = 1
        if isinstance(entry, dict):
            identifier = str(entry.get("item_id", "") or "")
            try:
                quantity = max(1, int(entry.get("quantity", 1) or 1))
            except (TypeError, ValueError):
                quantity = 1
        elif isinstance(entry, str):
            identifier = entry
        if not identifier:
            continue
        from engine.items.item_factory import ItemFactory

        for _ in range(quantity):
            item = ItemFactory.create_item_from_template(identifier, world)
            if item is None:
                report.failed.append("give_rewards item %s (missing template)" % identifier)
                break
            player.inventory.add_item(item)
            report.messages.append("You receive %s." % item.name)

    # A reward bundle may carry an already-generated item instance (procedural
    # loot rolled elsewhere). The topics path has always supported this, so the
    # shared interpreter must too.
    generated = rewards.get("generated_item_data")
    if isinstance(generated, dict):
        from engine.items.item_factory import ItemFactory

        item = ItemFactory.from_dict(generated, world)
        if item is None:
            report.failed.append("give_rewards generated_item_data (unreadable)")
        else:
            player.inventory.add_item(item)
            report.messages.append("You receive %s." % item.name)

    report.applied.append("rewards")


def apply_effects(effects: Any, context: Dict[str, Any]) -> EffectReport:
    """Apply every effect in `effects`. Never raises into the calling path.

    `context` carries `player`, `world`, and optionally `npc` (the speaker) and
    `quest_id` (the quest this conversation is part of).
    """
    report = EffectReport()
    if not effects:
        return report
    if not isinstance(effects, dict):
        report.unknown.append(str(effects))
        return report

    player = context.get("player")
    world = _context_world(context)
    if player is None:
        report.failed.append("no player")
        return report

    for key in sorted(effects):
        if key not in KNOWN_EFFECTS:
            report.unknown.append(key)

    try:
        _apply_quest_effects(effects, player, world, report)
        _apply_learning_effects(effects, player, report)
        _apply_item_effects(effects, player, world, report)
        _apply_relationship_effects(effects, context, report)
        _apply_flag_effect(effects, player, report)
        _apply_exit_effect(effects, context, report)
        _apply_move_npc_effect(effects, context, report)
        _apply_reward_effect(effects, player, world, report)
    except Exception as error:  # pragma: no cover - defensive
        # An effect is content. Content must not be able to break a
        # conversation; report it and carry on.
        report.failed.append("exception: %s" % error)

    return report


def describe_effects(effects: Any) -> str:
    """A short mechanical description for test mode."""
    if not isinstance(effects, dict) or not effects:
        return ""
    parts: List[str] = []
    for key in sorted(effects):
        value = effects[key]
        if isinstance(value, dict):
            rendered = ", ".join("%s=%s" % (k, v) for k, v in sorted(value.items()))
            parts.append("%s(%s)" % (key, rendered))
        elif isinstance(value, (list, tuple)):
            parts.append("%s[%s]" % (key, ", ".join(str(v) for v in value)))
        else:
            parts.append("%s=%s" % (key, value))
    return " ".join(parts)
