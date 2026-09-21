"""Content-neutral personal-relationship primitives shared by gameplay systems.

**The ladder is the content set's, or there is none.** What a relationship *is*
called, where its thresholds sit and what a bond is worth at a vendor are all
declared in `ruleset.social`; a set that declares nothing has no ladder, so it
shows no tier names and no discount. That is deliberate (2026-09-19): the engine
used to keep a fantasy-shaped default ladder, which meant a set that never
mentioned relationships rendered "Close Friend" and quietly discounted its
vendors' prices by up to 15%. A default that changes prices is not a default, it
is an undeclared rule.

Gift *scoring* still has engine defaults, because a gift has to be worth
something: a set that declares no `gift_values` gets the neutral numbers below,
and the words a player reads come from the ladder it declares.
"""

from typing import Any, Dict


# What a gift is worth when the set does not say. One score, no words: the labels
# and the thresholds are content's, and a set with no ladder never shows either.
DEFAULT_SOCIAL_RULES: Dict[str, Any] = {
    "gift_values": {"ordinary": 1, "crafted": 5, "preferred_item": 4, "preferred_category": 2, "disliked_item": -3},
}


def relationship_rules(world) -> Dict[str, Any]:
    authored = world.ruleset_section("social") if world is not None else {}
    merged = dict(DEFAULT_SOCIAL_RULES)
    if isinstance(authored, dict):
        merged.update({key: value for key, value in authored.items() if value is not None})
    return merged


def relationship_tiers(world=None) -> list[Dict[str, Any]]:
    """The ladder this set declared, highest threshold first. Empty means none."""
    raw = relationship_rules(world).get("tiers", [])
    if not isinstance(raw, list):
        return []
    tiers = [entry for entry in raw if isinstance(entry, dict) and isinstance(entry.get("min"), (int, float))]
    return sorted(tiers, key=lambda entry: int(entry["min"]), reverse=True)


def has_ladder(world) -> bool:
    """Whether this set presents bonds at all.

    One question, asked wherever a tier name, a score or a discount would
    otherwise appear, so "no ladder" is one decision rather than four checks that
    can drift apart.
    """
    return bool(relationship_tiers(world))


def relationship_key(npc) -> str:
    """Return the stable NPC identity used in player saves and content gates."""
    return str(getattr(npc, "template_id", "") or getattr(npc, "obj_id", ""))


def relationship_tier(score: int, world=None) -> str:
    """The tier a score sits in, or "" when this set declares no ladder."""
    for tier in relationship_tiers(world):
        if score >= int(tier["min"]):
            return str(tier.get("label", ""))
    return ""


def relationship_discount(score: int, world=None) -> float:
    for tier in relationship_tiers(world):
        if score >= int(tier["min"]):
            return max(0.0, min(0.95, float(tier.get("vendor_discount", 0.0))))
    return 0.0


def apply_relationship_milestones(player, npc, old_score: int, new_score: int, world) -> str:
    """Grant authored one-time threshold rewards without theme-specific rules."""
    if new_score <= old_score:
        return ""
    properties = getattr(npc, "properties", {})
    milestones = properties.get("relationship_milestones", []) if isinstance(properties, dict) else []
    if not isinstance(milestones, list):
        return ""
    key = relationship_key(npc)
    completed = player.relationship_milestones_completed.setdefault(key, [])
    messages = []
    for milestone in milestones:
        if not isinstance(milestone, dict):
            continue
        milestone_id = str(milestone.get("id", "")).strip()
        minimum = milestone.get("min")
        if not milestone_id or milestone_id in completed or isinstance(minimum, bool) or not isinstance(minimum, int):
            continue
        if old_score < minimum <= new_score:
            rewards = milestone.get("rewards", {})
            if not isinstance(rewards, dict):
                continue
            granted = []
            gold = rewards.get("gold", 0)
            if isinstance(gold, int) and gold > 0 and player.runtime_state.gold is not None:
                player.runtime_state.gold += gold
                granted.append(f"{gold} {world.currency_name()}")
            for item_data in rewards.get("items", []):
                if not isinstance(item_data, dict):
                    continue
                item_id = item_data.get("item_id")
                quantity = item_data.get("quantity", 1)
                if not isinstance(item_id, str) or not isinstance(quantity, int) or quantity < 1:
                    continue
                from engine.items.item_factory import ItemFactory
                item = ItemFactory.create_item_from_template(item_id, world)
                if item is None:
                    continue
                can_add, _reason = player.inventory.can_add_item(item, quantity)
                if can_add:
                    player.inventory.add_item(item, quantity)
                    granted.append(f"{quantity} x {item.name}")
            completed.append(milestone_id)
            message = str(milestone.get("message", "")).strip()
            summary = ", ".join(granted) if granted else "a new bond"
            messages.append((message + " " if message else "") + f"Milestone reached: {summary}.")

    # Crossing into a new tier is a recognised activity and pays advancement XP
    # once per tier (ROADMAP P4). Recorded separately from authored milestones:
    # the tier is the engine-visible relationship band, while a milestone is a
    # specific authored threshold. A set with no ladder has no tiers to cross, and
    # "" would compare equal to "" forever, so the award simply does not happen.
    old_tier = relationship_tier(old_score, world)
    new_tier = relationship_tier(new_score, world)
    if new_tier and new_tier != old_tier:
        from engine.core import advancement
        tier_note = advancement.award(
            player, advancement.KIND_RELATIONSHIP, new_tier,
            payload={"npc_id": str(getattr(npc, "template_id", "") or ""), "tier": new_tier},
        )
        if tier_note:
            messages.append(tier_note)

    return "\n".join(messages)


def next_relationship_milestone(player, npc, score: int) -> Dict[str, Any] | None:
    """Return the nearest unclaimed authored threshold, if the NPC has one."""
    properties = getattr(npc, "properties", {})
    milestones = properties.get("relationship_milestones", []) if isinstance(properties, dict) else []
    completed = set(getattr(player, "relationship_milestones_completed", {}).get(relationship_key(npc), []))
    candidates = [
        entry for entry in milestones
        if isinstance(entry, dict) and str(entry.get("id", "")).strip() not in completed
        and isinstance(entry.get("min"), int) and not isinstance(entry.get("min"), bool)
        and int(entry["min"]) > score
    ]
    return min(candidates, key=lambda entry: int(entry["min"])) if candidates else None
