"""Content-neutral personal-relationship primitives shared by gameplay systems."""

from typing import Any, Dict


DEFAULT_SOCIAL_RULES: Dict[str, Any] = {
    "gift_values": {"ordinary": 1, "crafted": 5, "preferred_item": 4, "preferred_category": 2, "disliked_item": -3},
    "tiers": [
        {"min": 60, "label": "Close Friend", "vendor_discount": 0.15},
        {"min": 30, "label": "Friend", "vendor_discount": 0.10},
        {"min": 10, "label": "Acquaintance", "vendor_discount": 0.05},
        {"min": 0, "label": "Stranger", "vendor_discount": 0.0},
    ],
}


def relationship_rules(world) -> Dict[str, Any]:
    authored = world.ruleset_section("social") if world is not None else {}
    merged = dict(DEFAULT_SOCIAL_RULES)
    if isinstance(authored, dict):
        merged.update({key: value for key, value in authored.items() if value is not None})
    return merged


def relationship_tiers(world=None) -> list[Dict[str, Any]]:
    raw = relationship_rules(world).get("tiers", [])
    tiers = [entry for entry in raw if isinstance(entry, dict) and isinstance(entry.get("min"), (int, float))]
    return sorted(tiers, key=lambda entry: int(entry["min"]), reverse=True) or list(DEFAULT_SOCIAL_RULES["tiers"])


def relationship_key(npc) -> str:
    """Return the stable NPC identity used in player saves and content gates."""
    return str(getattr(npc, "template_id", "") or getattr(npc, "obj_id", ""))


def relationship_tier(score: int, world=None) -> str:
    """Human-readable tier, with labels and thresholds authored by a content set."""
    for tier in relationship_tiers(world):
        if score >= int(tier["min"]):
            return str(tier.get("label", "Relationship"))
    return "Relationship"


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
