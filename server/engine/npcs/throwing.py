# engine/npcs/throwing.py
"""A creature that carries throwing things throws them: a ninja's knives, a goblin's pot of fire.

Any consumable in an NPC's pack (`initial_inventory`) whose `effect_type` is `target_damage` (with `damage_amount` and
`damage_type`, the same item a player hurls with `use <item> on <target>`) may be thrown at its target instead of a plain
blow. `properties.throw_chance` (0 to 1, default 0.5) is how often it does so while it has one; each throw spends one use.
"""

import random
from typing import Any, Dict, Optional

DEFAULT_THROW_CHANCE = 0.5


def throwable(npc: Any) -> Optional[Any]:
    inventory = getattr(npc, "inventory", None)
    for slot in getattr(inventory, "slots", None) or []:
        item = getattr(slot, "item", None)
        if item is None or item.get_property("effect_type") != "target_damage" or item.get_property("uses", 1) <= 0:
            continue
        amount = item.get_property("damage_amount")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0 and item.get_property("damage_type"):
            return item
    return None


def chance_of(npc: Any) -> float:
    value = (getattr(npc, "properties", {}) or {}).get("throw_chance", DEFAULT_THROW_CHANCE)
    return DEFAULT_THROW_CHANCE if isinstance(value, bool) or not isinstance(value, (int, float)) else max(0.0, min(1.0, float(value)))


def try_throw(npc: Any, target: Any) -> Optional[Dict[str, Any]]:
    """Throw one at `target`, or None (nothing to throw, or this turn it strikes instead). Same shape an `attack` returns."""
    item = throwable(npc)
    if item is None or random.random() >= chance_of(npc):
        return None
    from engine.utils.articles import the

    damage_type = str(item.get_property("damage_type"))
    taken = target.take_damage(int(item.get_property("damage_amount")), damage_type) if hasattr(target, "take_damage") else 0
    npc.inventory.remove_item(item.obj_id, 1)
    shown = getattr(target, "name", "its target")
    if taken > 0:
        message = "%s hurls %s at %s, dealing %d %s damage." % (npc.name, the(item.name), shown, taken, damage_type)
    else:
        message = "%s hurls %s at %s, but it does no harm." % (npc.name, the(item.name), shown)
    return {"message": message, "target_defeated": not getattr(target, "is_alive", True), "damage": taken}
