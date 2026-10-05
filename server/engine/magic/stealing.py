# engine/magic/stealing.py
"""Stealing in a fight: an ability with a `steal` effect takes something from the creature it is cast at.

A creature carries what can be taken in `properties.steal_items`: `[{"item_id": "item_ruby", "chance": 0.5}, ...]` (`chance`
is 0 to 1, default 0.6). Each is tried in turn, and once taken it is gone for good (`properties.stolen` remembers). The
thing goes to the caster, or to the owner of a companion that casts it.
"""

import random
from typing import Any, Dict, List, Optional

DEFAULT_CHANCE = 0.6
STEAL_ITEM_KEYS = ("item_id", "chance")


def _entries(target: Any) -> List[Dict[str, Any]]:
    properties = getattr(target, "properties", None)
    raw = properties.get("steal_items") if isinstance(properties, dict) else None
    return [entry for entry in raw if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)] if isinstance(raw, list) else []


def remaining(target: Any) -> List[Dict[str, Any]]:
    stolen = target.properties.get("stolen", []) if isinstance(getattr(target, "properties", None), dict) else []
    return [entry for entry in _entries(target) if entry["item_id"] not in stolen]


def worth_trying(target: Any) -> bool:
    """Whether there is still something to take (an AI does not waste its turn on a creature with nothing)."""
    return bool(remaining(target))


def _recipient(caster: Any) -> Any:
    if getattr(caster, "runtime_state", None) is not None:
        return caster
    world = getattr(caster, "world", None)
    owner_id = caster.properties.get("owner_id") if isinstance(getattr(caster, "properties", None), dict) else None
    return world.get_player_by_id(owner_id) if world is not None and owner_id else None


def attempt(caster: Any, target: Any) -> Optional[str]:
    """One try. The line to tell."""
    from engine.items.item_factory import ItemFactory

    who = getattr(caster, "name", "Someone")
    whom = getattr(target, "name", "it")
    left = remaining(target)
    if not left:
        return "%s finds nothing on %s to take." % (who, whom)
    entry = left[0]
    chance = entry.get("chance", DEFAULT_CHANCE)
    chance = DEFAULT_CHANCE if isinstance(chance, bool) or not isinstance(chance, (int, float)) else max(0.0, min(1.0, float(chance)))
    if random.random() >= chance:
        return "%s reaches for something on %s, but comes away with nothing." % (who, whom)
    recipient = _recipient(caster)
    world = getattr(caster, "world", None)
    item = ItemFactory.create_item_from_template(entry["item_id"], world) if world is not None else None
    inventory = getattr(recipient, "inventory", None)
    if item is None or inventory is None:
        return "%s fails to take anything from %s." % (who, whom)
    inventory.add_item(item)
    target.properties.setdefault("stolen", []).append(entry["item_id"])
    return "%s steals %s from %s!" % (who, item.name, whom)
